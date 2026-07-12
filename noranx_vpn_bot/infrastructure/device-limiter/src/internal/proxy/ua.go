package proxy

import "strings"

var vpnClientPatterns = []string{
	"v2ray", "sing-box", "singbox", "hiddify", "clash", "stash",
	"shadowrocket", "quantumult", "surge", "nekoray", "nekobox",
	"matsuri", "sagernet", "loon", "pharos", "passwall", "ssrplus",
}

var nonCountablePatterns = []string{
	"telegrambot", "twitterbot", "facebookexternalhit", "slackbot",
	"discordbot", "whatsapp", "linkedinbot", "googlebot", "bingbot",
	"curl/", "wget/", "go-http-client", "python-requests", "postman",
}

// shouldCountDevice returns false for link-preview bots and in-app browsers
// that are not VPN clients. Those requests are proxied without tracking.
func shouldCountDevice(userAgent string) bool {
	ua := strings.ToLower(strings.TrimSpace(userAgent))
	if ua == "" {
		return false
	}
	for _, p := range nonCountablePatterns {
		if strings.Contains(ua, p) {
			return false
		}
	}
	for _, p := range vpnClientPatterns {
		if strings.Contains(ua, p) {
			return true
		}
	}
	// Generic browsers (Telegram in-app browser, Chrome, Safari, etc.)
	if strings.Contains(ua, "mozilla/") {
		return false
	}
	// Unknown clients: count conservatively (custom apps, old clients).
	return true
}

func isVPNClientUserAgent(userAgent string) bool {
	ua := strings.ToLower(strings.TrimSpace(userAgent))
	for _, p := range vpnClientPatterns {
		if strings.Contains(ua, p) {
			return true
		}
	}
	return false
}
