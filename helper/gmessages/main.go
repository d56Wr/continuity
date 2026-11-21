// continuity-gmessages: a small bridge between Continuity and Google Messages for Web
// (SMS + RCS) built on mautrix-gmessages' libgm.
//
// Protocol: one JSON object per line.
//
//	stdin  (commands):  {"id": 1, "cmd": "conversations", ...}
//	stdout (replies):   {"id": 1, "ok": true, "result": ...} | {"id": 1, "error": "..."}
//	stdout (events):    {"event": "message", "data": {...}}
//
// The session (pairing keys) is stored in the file given with -session (mode 0600).
//
// SPDX-License-Identifier: AGPL-3.0-or-later
package main

import (
	"bufio"
	"context"
	"crypto/aes"
	"crypto/cipher"
	"crypto/hmac"
	"crypto/sha1"
	"encoding/base64"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/rs/zerolog"
	qrcode "github.com/skip2/go-qrcode"
	"go.mau.fi/util/exhttp"

	"go.mau.fi/mautrix-gmessages/pkg/libgm"
	"go.mau.fi/mautrix-gmessages/pkg/libgm/events"
	"go.mau.fi/mautrix-gmessages/pkg/libgm/gmproto"
)

var (
	sessionPath = flag.String("session", "", "path of the session file")
	mediaDir    = flag.String("media", "", "directory for downloaded media")
	verbose     = flag.Bool("v", false, "verbose libgm logging to stderr")

	out   = json.NewEncoder(os.Stdout)
	outMu sync.Mutex

	log zerolog.Logger

	mu      sync.Mutex
	cli     *libgm.Client
	auth    *libgm.AuthData
	convs   = map[string]*gmproto.Conversation{}
	bgCtx   context.Context
	cancelQ context.CancelFunc
)

func emit(v any) {
	outMu.Lock()
	defer outMu.Unlock()
	_ = out.Encode(v)
}

func event(name string, data any) { emit(map[string]any{"event": name, "data": data}) }

// ------------------------------------------------------------------ JSON shapes

type jParticipant struct {
	ID     string `json:"id"`
	Name   string `json:"name"`
	First  string `json:"first"`
	Number string `json:"number"`
	Color  string `json:"color"`
	IsMe   bool   `json:"isMe"`
}

type jConversation struct {
	ID           string         `json:"id"`
	Name         string         `json:"name"`
	Unread       bool           `json:"unread"`
	Timestamp    int64          `json:"timestamp"` // ms
	Snippet      string         `json:"snippet"`
	SnippetFrom  string         `json:"snippetFrom"`
	FromMe       bool           `json:"fromMe"`
	Type         string         `json:"type"` // sms | rcs
	Group        bool           `json:"group"`
	Pinned       bool           `json:"pinned"`
	ReadOnly     bool           `json:"readOnly"`
	Archived     bool           `json:"archived"`
	Color        string         `json:"color"`
	LatestID     string         `json:"latestId"`
	Participants []jParticipant `json:"participants"`
}

type jMedia struct {
	ID       string `json:"id"`
	Key      string `json:"key"`
	ThumbID  string `json:"thumbId"`
	ThumbKey string `json:"thumbKey"`
	Mime     string `json:"mime"`
	Name     string `json:"name"`
	Size     int64  `json:"size"`
	Width    int64  `json:"width"`
	Height   int64  `json:"height"`
}

type jReaction struct {
	Emoji string `json:"emoji"`
	Count int    `json:"count"`
	Mine  bool   `json:"mine"`
}

type jMessage struct {
	ID           string      `json:"id"`
	TmpID        string      `json:"tmpId"`
	Conversation string      `json:"conversation"`
	Timestamp    int64       `json:"timestamp"` // ms
	Sender       string      `json:"sender"`    // participant id
	SenderName   string      `json:"senderName"`
	FromMe       bool        `json:"fromMe"`
	Status       string      `json:"status"` // sending | sent | delivered | read | failed | received
	Text         string      `json:"text"`
	Subject      string      `json:"subject"`
	Media        []jMedia    `json:"media"`
	Reactions    []jReaction `json:"reactions"`
	ReplyTo      string      `json:"replyTo"`
	RCS          bool        `json:"rcs"`
	Old          bool        `json:"old"`
	Deleted      bool        `json:"deleted"`
}

func convJSON(c *gmproto.Conversation) jConversation {
	j := jConversation{
		ID: c.GetConversationID(), Name: c.GetName(), Unread: c.GetUnread(),
		Timestamp:   c.GetLastMessageTimestamp() / 1000,
		Snippet:     c.GetLatestMessage().GetDisplayContent(),
		SnippetFrom: c.GetLatestMessage().GetDisplayName(),
		FromMe:      c.GetLatestMessage().GetFromMe() == 1,
		Type:        "sms", Group: c.GetIsGroupChat(), Pinned: c.GetPinned(), ReadOnly: c.GetReadOnly(),
		Archived: c.GetStatus() == gmproto.ConversationStatus_ARCHIVED,
		Color:    c.GetAvatarHexColor(), LatestID: c.GetLatestMessageID(),
	}
	if c.GetType() == gmproto.ConversationType_RCS {
		j.Type = "rcs"
	}
	for _, p := range c.GetParticipants() {
		j.Participants = append(j.Participants, jParticipant{
			ID: p.GetID().GetParticipantID(), Name: p.GetFullName(), First: p.GetFirstName(),
			Number: firstNonEmpty(p.GetFormattedNumber(), p.GetID().GetNumber()),
			Color:  p.GetAvatarHexColor(), IsMe: p.GetIsMe(),
		})
	}
	return j
}

func statusString(s gmproto.MessageStatusType) (string, bool) {
	n := int32(s)
	if n >= 100 {
		return "received", false
	}
	switch s {
	case gmproto.MessageStatusType_OUTGOING_DELIVERED:
		return "delivered", true
	case gmproto.MessageStatusType_OUTGOING_DISPLAYED:
		return "read", true
	case gmproto.MessageStatusType_OUTGOING_COMPLETE:
		return "sent", true
	case gmproto.MessageStatusType_OUTGOING_YET_TO_SEND, gmproto.MessageStatusType_OUTGOING_SENDING,
		gmproto.MessageStatusType_OUTGOING_RESENDING, gmproto.MessageStatusType_OUTGOING_AWAITING_RETRY,
		gmproto.MessageStatusType_OUTGOING_SEND_AFTER_PROCESSING, gmproto.MessageStatusType_OUTGOING_VALIDATING,
		gmproto.MessageStatusType_OUTGOING_NOT_DELIVERED_YET, gmproto.MessageStatusType_OUTGOING_SCHEDULED,
		gmproto.MessageStatusType_OUTGOING_DRAFT:
		return "sending", true
	case gmproto.MessageStatusType_OUTGOING_DELETED:
		return "deleted", true
	}
	if n == 0 {
		return "received", false
	}
	return "failed", true
}

func msgJSON(m *gmproto.Message, old bool) jMessage {
	status, fromMe := statusString(m.GetMessageStatus().GetStatus())
	j := jMessage{
		ID: m.GetMessageID(), TmpID: m.GetTmpID(), Conversation: m.GetConversationID(),
		Timestamp: m.GetTimestamp() / 1000, Sender: m.GetParticipantID(), FromMe: fromMe,
		Status: status, Subject: m.GetSubject(), RCS: m.GetType() == 4, Old: old,
		Deleted: m.GetMessageStatus().GetStatus() == gmproto.MessageStatusType_INCOMING_DELETED ||
			m.GetMessageStatus().GetStatus() == gmproto.MessageStatusType_OUTGOING_DELETED,
	}
	if sp := m.GetSenderParticipant(); sp != nil {
		j.SenderName = sp.GetFullName()
		if sp.GetIsMe() {
			j.FromMe = true
		}
	}
	var texts []string
	for _, info := range m.GetMessageInfo() {
		if mc := info.GetMessageContent(); mc != nil && mc.GetContent() != "" {
			texts = append(texts, mc.GetContent())
		}
		if md := info.GetMediaContent(); md != nil {
			j.Media = append(j.Media, jMedia{
				ID: md.GetMediaID(), Key: base64.StdEncoding.EncodeToString(md.GetDecryptionKey()),
				ThumbID: md.GetThumbnailMediaID(), ThumbKey: base64.StdEncoding.EncodeToString(md.GetThumbnailDecryptionKey()),
				Mime: md.GetMimeType(), Name: md.GetMediaName(), Size: md.GetSize(),
				Width: md.GetDimensions().GetWidth(), Height: md.GetDimensions().GetHeight(),
			})
		}
		if loc := info.GetLocationContent(); loc != nil && len(texts) == 0 {
			texts = append(texts, "📍")
		}
	}
	j.Text = strings.Join(texts, "\n")
	for _, r := range m.GetReactions() {
		mine := false
		for _, pid := range r.GetParticipantIDs() {
			if c := convs[m.GetConversationID()]; c != nil {
				for _, p := range c.GetParticipants() {
					if p.GetIsMe() && p.GetID().GetParticipantID() == pid {
						mine = true
					}
				}
			}
		}
		j.Reactions = append(j.Reactions, jReaction{Emoji: r.GetData().GetUnicode(), Count: len(r.GetParticipantIDs()), Mine: mine})
	}
	if rm := m.GetReplyMessage(); rm != nil {
		j.ReplyTo = rm.GetMessageID()
	}
	return j
}

func firstNonEmpty(v ...string) string {
	for _, s := range v {
		if s != "" {
			return s
		}
	}
	return ""
}

// ------------------------------------------------------------------ session

func saveSession() {
	mu.Lock()
	a := auth
	mu.Unlock()
	if a == nil || *sessionPath == "" {
		return
	}
	data, err := json.Marshal(a)
	if err != nil {
		return
	}
	tmp := *sessionPath + ".tmp"
	if err := os.WriteFile(tmp, data, 0o600); err == nil {
		_ = os.Rename(tmp, *sessionPath)
	}
}

func loadSession() *libgm.AuthData {
	data, err := os.ReadFile(*sessionPath)
	if err != nil {
		return nil
	}
	a := libgm.NewAuthData()
	if json.Unmarshal(data, a) != nil {
		return nil
	}
	return a
}

// ------------------------------------------------------------------ events

func handleEvent(raw any) {
	switch evt := raw.(type) {
	case *events.ClientReady:
		mu.Lock()
		for _, c := range evt.Conversations {
			convs[c.GetConversationID()] = c
		}
		mu.Unlock()
		list := make([]jConversation, 0, len(evt.Conversations))
		for _, c := range evt.Conversations {
			list = append(list, convJSON(c))
		}
		event("conversations", map[string]any{"conversations": list})
	case *gmproto.Conversation:
		mu.Lock()
		convs[evt.GetConversationID()] = evt
		mu.Unlock()
		event("conversation", convJSON(evt))
	case *libgm.WrappedMessage:
		event("message", msgJSON(evt.Message, evt.IsOld))
	case *gmproto.TypingData:
		event("typing", map[string]any{"conversation": evt.GetConversationID(),
			"participant": evt.GetUser().GetNumber(), "typing": evt.GetType() == gmproto.TypingTypes_STARTED_TYPING})
	case *events.BrowserActive:
		event("inactive", map[string]any{"reason": "another_browser"})
	case *events.AuthTokenRefreshed:
		saveSession()
	case *events.PhoneNotResponding:
		event("phone", map[string]any{"responding": false})
	case *events.PhoneRespondingAgain:
		event("phone", map[string]any{"responding": true})
	case *events.ListenFatalError:
		event("error", map[string]any{"fatal": true, "message": evt.Error.Error()})
	case *events.ListenTemporaryError:
		event("error", map[string]any{"fatal": false, "message": evt.Error.Error()})
	case *events.ListenRecovered:
		event("recovered", nil)
	case *events.GaiaLoggedOut:
		event("logged_out", nil)
	case *gmproto.RevokePairData:
		event("logged_out", nil)
	case *events.PairSuccessful:
		// handled by the pair callback
	default:
		log.Debug().Type("type", raw).Msg("unhandled event")
	}
}

// ------------------------------------------------------------------ commands

type command struct {
	ID           int64             `json:"id"`
	Cmd          string            `json:"cmd"`
	Conversation string            `json:"conversation"`
	Message      string            `json:"message"`
	Text         string            `json:"text"`
	Count        int64             `json:"count"`
	Cursor       *gmproto.Cursor   `json:"cursor"`
	MediaID      string            `json:"mediaId"`
	Key          string            `json:"key"`
	Numbers      []string          `json:"numbers"`
	Emoji        string            `json:"emoji"`
	Remove       bool              `json:"remove"`
	Typing       bool              `json:"typing"`
	Cookies      map[string]string `json:"cookies"`
	Encrypted    []encCookie       `json:"encrypted"`
	DBVersion    int               `json:"dbVersion"`
	File         string            `json:"file"`
	Mime         string            `json:"mime"`
	ReplyTo      string            `json:"replyTo"`
}

func newClient(a *libgm.AuthData) *libgm.Client {
	c := libgm.NewClient(a, nil, log, exhttp.SensibleClientSettings)
	c.SetEventHandler(handleEvent)
	return c
}

func connect() error {
	mu.Lock()
	a := auth
	mu.Unlock()
	if a == nil {
		return errors.New("not paired")
	}
	c := newClient(a)
	mu.Lock()
	cli = c
	mu.Unlock()
	if err := c.Connect(bgCtx); err != nil {
		return err
	}
	afterConnect(c)
	return nil
}

// afterConnect makes this the active web session and tells the UI it can load data.
// (libgm only sends ClientReady on some connection paths, e.g. not after Google pairing.)
func afterConnect(c *libgm.Client) {
	if err := c.SetActiveSession(bgCtx); err != nil {
		log.Warn().Err(err).Msg("set active session failed")
	}
	event("ready", map[string]any{"conversations": []jConversation{}})
}

func startQR() (any, error) {
	if cancelQ != nil {
		cancelQ()
	}
	a := libgm.NewAuthData()
	c := libgm.NewClient(a, nil, log, exhttp.SensibleClientSettings)
	c.SetEventHandler(func(any) {})
	paired := make(chan *gmproto.PairedData, 1)
	cb := func(data *gmproto.PairedData) { paired <- data }
	c.PairCallback.Store(&cb)
	if err := c.FetchConfig(bgCtx); err != nil {
		return nil, err
	}
	ctx, cancel := context.WithCancel(bgCtx)
	cancelQ = cancel
	qr, err := c.StartLogin(ctx)
	if err != nil {
		cancel()
		return nil, err
	}
	go func() {
		ticker := time.NewTicker(30 * time.Second)
		defer ticker.Stop()
		for tries := 0; ; tries++ {
			select {
			case data := <-paired:
				c.Disconnect()
				_ = os.Remove(filepath.Join(filepath.Dir(*sessionPath), "pair-qr.png"))
				mu.Lock()
				auth = a
				mu.Unlock()
				saveSession()
				event("paired", map[string]any{"phone": data.GetMobile().GetSourceID()})
				time.Sleep(2 * time.Second) // let the phone store the pairing before reconnecting
				if err := connect(); err != nil {
					event("error", map[string]any{"fatal": true, "message": err.Error()})
				}
				return
			case <-ticker.C:
				if tries >= 8 {
					c.Disconnect()
					event("qr_expired", nil)
					return
				}
				if next, err := c.RefreshPhoneRelay(); err == nil {
					event("qr", qrPayload(next))
				}
			case <-ctx.Done():
				c.Disconnect()
				return
			}
		}
	}()
	return qrPayload(qr), nil
}

// encCookie is a row of a Chromium cookie database started with --password-store=basic.
type encCookie struct {
	Name  string `json:"name"`
	Host  string `json:"host"`
	Value string `json:"value"` // plain value (rare) …
	Enc   []byte `json:"enc"`   // … or encrypted_value (base64 in JSON)
}

// decryptChromiumCookies decrypts "v10" cookies of a Chromium profile that uses the basic
// (non-keyring) password store: AES-128-CBC, key = PBKDF2-SHA1("peanuts", "saltysalt", 1 iteration).
// Database schema version >= 24 prefixes the plaintext with SHA-256(host).
func decryptChromiumCookies(rows []encCookie, dbVersion int) map[string]string {
	mac := hmac.New(sha1.New, []byte("peanuts"))
	mac.Write([]byte("saltysalt\x00\x00\x00\x01"))
	key := mac.Sum(nil)[:16]
	block, _ := aes.NewCipher(key)
	iv := []byte("                ")
	want := map[string]string{"OSID": "messages.google.com", "SID": ".google.com", "HSID": ".google.com",
		"SSID": ".google.com", "APISID": ".google.com", "SAPISID": ".google.com", "__Secure-1PSIDTS": ".google.com"}
	out := map[string]string{}
	for _, r := range rows {
		dom, ok := want[r.Name]
		if !ok || strings.TrimPrefix(r.Host, ".") != strings.TrimPrefix(dom, ".") {
			continue
		}
		if r.Value != "" {
			out[r.Name] = r.Value
			continue
		}
		if len(r.Enc) < 3+aes.BlockSize || string(r.Enc[:3]) != "v10" {
			continue
		}
		data := append([]byte(nil), r.Enc[3:]...)
		if len(data)%aes.BlockSize != 0 {
			continue
		}
		cipher.NewCBCDecrypter(block, iv).CryptBlocks(data, data)
		pad := int(data[len(data)-1])
		if pad == 0 || pad > aes.BlockSize || pad > len(data) {
			continue
		}
		data = data[:len(data)-pad]
		if dbVersion >= 24 && len(data) >= 32 {
			data = data[32:]
		}
		out[r.Name] = string(data)
	}
	return out
}

func isPaired(a *libgm.AuthData) bool {
	return a != nil && (a.Browser != nil || (a.Mobile != nil && len(a.TachyonAuthToken) > 0))
}

// startGoogle pairs through a Google account: the cookies come from a browser session
// signed in to messages.google.com; the user then taps the matching emoji on the phone.
func startGoogle(cookies map[string]string) (any, error) {
	for _, k := range []string{"SID", "HSID", "SSID", "APISID", "SAPISID", "OSID"} {
		if cookies[k] == "" {
			return nil, fmt.Errorf("missing cookie %s", k)
		}
	}
	a := libgm.NewAuthData()
	a.SetCookies(cookies)
	c := libgm.NewClient(a, nil, log, exhttp.SensibleClientSettings)
	c.SetEventHandler(handleEvent)
	if err := c.FetchConfig(bgCtx); err != nil {
		return nil, fmt.Errorf("google rejected the session: %w", err)
	}
	go func() {
		err := c.DoGaiaPairing(bgCtx, func(emoji string) {
			event("pair_emoji", map[string]any{"emoji": emoji, "svg": libgm.GetEmojiSVG(emoji)})
		})
		if err != nil {
			msg := err.Error()
			switch {
			case errors.Is(err, libgm.ErrIncorrectEmoji):
				msg = "wrong_emoji"
			case errors.Is(err, libgm.ErrNoDevicesFound), errors.Is(err, libgm.ErrPhoneNotFound):
				msg = "no_phone"
			case errors.Is(err, libgm.ErrPhoneInactive):
				msg = "phone_inactive"
			}
			c.Disconnect()
			event("pair_failed", map[string]any{"reason": msg})
			return
		}
		mu.Lock()
		auth = a
		cli = c // DoGaiaPairing reconnects this client by itself
		mu.Unlock()
		saveSession()
		event("paired", map[string]any{"google": true})
		for i := 0; i < 60 && !c.IsConnected(); i++ {
			time.Sleep(500 * time.Millisecond)
		}
		afterConnect(c)
	}()
	return map[string]any{"started": true}, nil
}

// qrPayload returns the pairing URL plus a PNG rendering of it for the UI.
func qrPayload(url string) map[string]any {
	res := map[string]any{"url": url}
	path := filepath.Join(filepath.Dir(*sessionPath), "pair-qr.png")
	if err := qrcode.WriteFile(url, qrcode.Medium, 512, path); err == nil {
		res["png"] = path
	}
	return res
}

func conv(id string) (*gmproto.Conversation, error) {
	mu.Lock()
	c := convs[id]
	mu.Unlock()
	if c != nil {
		return c, nil
	}
	c, err := cli.GetConversation(bgCtx, id)
	if err == nil {
		mu.Lock()
		convs[id] = c
		mu.Unlock()
	}
	return c, err
}

func outgoingParticipant(c *gmproto.Conversation) string {
	if id := c.GetDefaultOutgoingID(); id != "" {
		return id
	}
	for _, p := range c.GetParticipants() {
		if p.GetIsMe() {
			return p.GetID().GetParticipantID()
		}
	}
	return ""
}

func run(cmd command) (any, error) {
	if cmd.Cmd == "status" {
		mu.Lock()
		defer mu.Unlock()
		return map[string]any{"paired": isPaired(auth),
			"connected": cli != nil && cli.IsConnected()}, nil
	}
	if cmd.Cmd == "pair_qr" {
		return startQR()
	}
	if cmd.Cmd == "pair_google" {
		cookies := cmd.Cookies
		if len(cmd.Encrypted) > 0 {
			cookies = decryptChromiumCookies(cmd.Encrypted, cmd.DBVersion)
		}
		return startGoogle(cookies)
	}
	if cmd.Cmd == "connect" {
		return nil, connect()
	}
	if cli == nil {
		return nil, errors.New("not connected")
	}
	switch cmd.Cmd {
	case "conversations":
		n := cmd.Count
		if n <= 0 {
			n = 100
		}
		resp, err := cli.ListConversations(bgCtx, &gmproto.ListConversationsRequest{
			Count: n, Folder: gmproto.ListConversationsRequest_INBOX, Cursor: cmd.Cursor})
		if err != nil {
			return nil, err
		}
		list := []jConversation{}
		mu.Lock()
		for _, c := range resp.GetConversations() {
			convs[c.GetConversationID()] = c
			list = append(list, convJSON(c))
		}
		mu.Unlock()
		return map[string]any{"conversations": list, "cursor": resp.GetCursor()}, nil
	case "messages":
		n := cmd.Count
		if n <= 0 {
			n = 50
		}
		resp, err := cli.FetchMessages(bgCtx, cmd.Conversation, n, cmd.Cursor)
		if err != nil {
			return nil, err
		}
		msgs := []jMessage{}
		for _, m := range resp.GetMessages() {
			msgs = append(msgs, msgJSON(m, true))
		}
		return map[string]any{"messages": msgs, "cursor": resp.GetCursor(), "total": resp.GetTotalMessages()}, nil
	case "send":
		c, err := conv(cmd.Conversation)
		if err != nil {
			return nil, err
		}
		tmp := fmt.Sprintf("tmp_%d", time.Now().UnixNano()%1_000_000_000_000)
		infos := []*gmproto.MessageInfo{}
		if cmd.File != "" {
			data, err := os.ReadFile(cmd.File)
			if err != nil {
				return nil, err
			}
			media, err := cli.UploadMedia(bgCtx, data, filepath.Base(cmd.File), cmd.Mime)
			if err != nil {
				return nil, err
			}
			infos = append(infos, &gmproto.MessageInfo{Data: &gmproto.MessageInfo_MediaContent{MediaContent: media}})
		}
		if cmd.Text != "" {
			infos = append(infos, &gmproto.MessageInfo{Data: &gmproto.MessageInfo_MessageContent{
				MessageContent: &gmproto.MessageContent{Content: cmd.Text}}})
		}
		req := &gmproto.SendMessageRequest{
			ConversationID: c.GetConversationID(),
			MessagePayload: &gmproto.MessagePayload{
				TmpID: tmp, TmpID2: tmp, ConversationID: c.GetConversationID(),
				ParticipantID: outgoingParticipant(c), MessageInfo: infos,
			},
			SIMPayload: c.GetSimCard().GetSIMData().GetSIMPayload(),
			TmpID:      tmp,
			ForceRCS:   c.GetType() == gmproto.ConversationType_RCS && c.GetSendMode() == gmproto.ConversationSendMode_SEND_MODE_AUTO,
		}
		if cmd.ReplyTo != "" {
			req.Reply = &gmproto.ReplyPayload{MessageID: cmd.ReplyTo}
		}
		resp, err := cli.SendMessage(bgCtx, req)
		if err != nil {
			return nil, err
		}
		if resp.GetStatus() != gmproto.SendMessageResponse_SUCCESS {
			return nil, fmt.Errorf("send failed: %s", resp.GetStatus())
		}
		return map[string]any{"tmpId": tmp}, nil
	case "new_conversation":
		nums := []*gmproto.ContactNumber{}
		for _, n := range cmd.Numbers {
			nums = append(nums, &gmproto.ContactNumber{MysteriousInt: 2, Number: n, Number2: n})
		}
		resp, err := cli.GetOrCreateConversation(bgCtx, &gmproto.GetOrCreateConversationRequest{Numbers: nums})
		if err != nil {
			return nil, err
		}
		c := resp.GetConversation()
		if c == nil {
			return nil, fmt.Errorf("could not open conversation (%s)", resp.GetStatus())
		}
		mu.Lock()
		convs[c.GetConversationID()] = c
		mu.Unlock()
		return convJSON(c), nil
	case "mark_read":
		return nil, cli.MarkRead(bgCtx, cmd.Conversation, cmd.Message)
	case "typing":
		c, err := conv(cmd.Conversation)
		if err != nil {
			return nil, err
		}
		return nil, cli.SetTyping(bgCtx, cmd.Conversation, cmd.Typing, c.GetSimCard().GetSIMData().GetSIMPayload())
	case "react":
		action := gmproto.SendReactionRequest_ADD
		if cmd.Remove {
			action = gmproto.SendReactionRequest_REMOVE
		}
		_, err := cli.SendReaction(bgCtx, &gmproto.SendReactionRequest{
			MessageID: cmd.Message, ReactionData: gmproto.MakeReactionData(cmd.Emoji), Action: action})
		return nil, err
	case "delete_message":
		_, err := cli.DeleteMessage(bgCtx, cmd.Message)
		return nil, err
	case "download":
		key, err := base64.StdEncoding.DecodeString(cmd.Key)
		if err != nil {
			return nil, err
		}
		path := filepath.Join(*mediaDir, safeName(cmd.MediaID))
		if _, err := os.Stat(path); err == nil {
			return map[string]any{"path": path}, nil
		}
		r, err := cli.DownloadMedia(bgCtx, cmd.MediaID, key)
		if err != nil {
			return nil, err
		}
		defer r.Close()
		_ = os.MkdirAll(*mediaDir, 0o700)
		f, err := os.CreateTemp(*mediaDir, ".dl-*")
		if err != nil {
			return nil, err
		}
		_, err = io.Copy(f, r)
		_ = f.Close()
		if err != nil {
			_ = os.Remove(f.Name())
			return nil, err
		}
		return map[string]any{"path": path}, os.Rename(f.Name(), path)
	case "activate":
		return nil, cli.SetActiveSession(bgCtx)
	case "unpair":
		err := cli.Unpair(bgCtx)
		mu.Lock()
		auth = nil
		mu.Unlock()
		_ = os.Remove(*sessionPath)
		return nil, err
	}
	return nil, fmt.Errorf("unknown command %q", cmd.Cmd)
}

func safeName(id string) string {
	return strings.Map(func(r rune) rune {
		if r == '/' || r == '\\' || r == 0 || r == '.' {
			return '_'
		}
		return r
	}, id)
}

func main() {
	flag.Parse()
	level := zerolog.WarnLevel
	if *verbose {
		level = zerolog.DebugLevel
	}
	log = zerolog.New(zerolog.ConsoleWriter{Out: os.Stderr, TimeFormat: time.Stamp}).Level(level).With().Timestamp().Logger()
	if *sessionPath == "" {
		fmt.Fprintln(os.Stderr, "-session is required")
		os.Exit(2)
	}
	if *mediaDir == "" {
		*mediaDir = filepath.Join(filepath.Dir(*sessionPath), "media")
	}
	var cancel context.CancelFunc
	bgCtx, cancel = context.WithCancel(log.WithContext(context.Background()))
	defer cancel()

	auth = loadSession()
	if isPaired(auth) {
		event("starting", map[string]any{"paired": true})
		go func() {
			if err := connect(); err != nil {
				event("error", map[string]any{"fatal": true, "message": err.Error()})
			}
		}()
	} else {
		auth = nil
		event("starting", map[string]any{"paired": false})
	}

	scan := bufio.NewScanner(os.Stdin)
	scan.Buffer(make([]byte, 1<<20), 16<<20)
	for scan.Scan() {
		var cmd command
		if err := json.Unmarshal(scan.Bytes(), &cmd); err != nil {
			emit(map[string]any{"error": "bad json: " + err.Error()})
			continue
		}
		go func(cmd command) {
			res, err := run(cmd)
			if err != nil {
				emit(map[string]any{"id": cmd.ID, "error": err.Error()})
				return
			}
			emit(map[string]any{"id": cmd.ID, "ok": true, "result": res})
		}(cmd)
	}
	saveSession()
	if cli != nil {
		cli.Disconnect()
	}
}
