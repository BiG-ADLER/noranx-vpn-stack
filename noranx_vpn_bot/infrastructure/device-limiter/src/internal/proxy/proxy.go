package proxy

import (
	"crypto/sha256"
	"crypto/tls"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"strings"

	"github.com/kets/qentvpn/marzban-device-limit/internal/db"
	"github.com/kets/qentvpn/marzban-device-limit/internal/model"
)

var hwidHeaderNames = []string{
	"X-HWID",
	"X-Device-Id",
	"X-Sing-Box-HWID",
	"X-Singbox-HWID",
	"X-Hiddify-Client-Id",
}

func NewProxy(targetURL string) *httputil.ReverseProxy {
	target, err := url.Parse(targetURL)
	if err != nil {
		log.Fatal("Invalid proxy target:", err)
	}
	p := httputil.NewSingleHostReverseProxy(target)
	if target.Scheme == "https" {
		p.Transport = &http.Transport{
			TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
		}
	}
	return p
}

func Handler(p *httputil.ReverseProxy) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if !strings.HasPrefix(r.URL.Path, "/sub/") {
			p.ServeHTTP(w, r)
			return
		}

		token := extractSubToken(r.URL.Path)
		username := extractUsernameFromToken(token)

		if username == "" {
			p.ServeHTTP(w, r)
			return
		}

		hwid := extractHWID(r)
		userAgent := r.Header.Get("User-Agent")
		fingerprint := hwid
		if fingerprint == "" {
			fingerprint = buildFallbackFingerprint(r, token, userAgent)
		}

		limitConfig, err := db.GetUserLimit(username)
		if err != nil {
			log.Printf("Error getting limit for %s: %v", username, err)
			http.Error(w, "Device limiter unavailable", http.StatusServiceUnavailable)
			return
		}

		if !limitConfig.Configured || !limitConfig.HWIDEnabled {
			p.ServeHTTP(w, r)
			return
		}

		if !shouldCountDevice(userAgent) {
			p.ServeHTTP(w, r)
			return
		}

		err = db.TrackDevice(model.Device{
			Username:    username,
			HWID:        hwid,
			UserAgent:   userAgent,
			Fingerprint: fingerprint,
		})
		if err != nil {
			log.Printf("Error tracking device for %s: %v", username, err)
			http.Error(w, "Device limiter unavailable", http.StatusServiceUnavailable)
			return
		}

		count, err := db.GetDeviceCount(username)
		if err != nil {
			log.Printf("Error counting devices for %s: %v", username, err)
			http.Error(w, "Device limiter unavailable", http.StatusServiceUnavailable)
			return
		}

		if count > limitConfig.DeviceLimit {
			log.Printf(
				"Limit exceeded for %s: %d/%d (FP: %s HWID: %t UA: %s)",
				username, count, limitConfig.DeviceLimit, fingerprint, hwid != "", userAgent,
			)
			http.Error(w, "Device limit exceeded", http.StatusForbidden)
			return
		}

		p.ServeHTTP(w, r)
	}
}

func extractSubToken(path string) string {
	trimmed := strings.TrimPrefix(path, "/sub/")
	trimmed = strings.Trim(trimmed, "/")
	if idx := strings.Index(trimmed, "/"); idx >= 0 {
		trimmed = trimmed[:idx]
	}
	return trimmed
}

func extractHWID(r *http.Request) string {
	for _, name := range hwidHeaderNames {
		if v := strings.TrimSpace(r.Header.Get(name)); v != "" {
			return v
		}
	}
	return ""
}

func clientIPFromRequest(r *http.Request) string {
	if v := strings.TrimSpace(r.Header.Get("X-Real-IP")); v != "" {
		return v
	}
	if xff := strings.TrimSpace(r.Header.Get("X-Forwarded-For")); xff != "" {
		if idx := strings.Index(xff, ","); idx >= 0 {
			return strings.TrimSpace(xff[:idx])
		}
		return xff
	}
	if host, _, err := net.SplitHostPort(strings.TrimSpace(r.RemoteAddr)); err == nil && host != "" {
		return host
	}
	return strings.TrimSpace(r.RemoteAddr)
}

func buildFallbackFingerprint(r *http.Request, token, userAgent string) string {
	parts := []string{userAgent, token}
	// VPN clients without HWID: stable fingerprint per app install (ignore IP / browser hints).
	if !isVPNClientUserAgent(userAgent) {
		if v := clientIPFromRequest(r); v != "" {
			parts = append(parts, v)
		}
		if v := r.Header.Get("Accept-Language"); v != "" {
			parts = append(parts, v)
		}
		if v := r.Header.Get("Sec-CH-UA"); v != "" {
			parts = append(parts, v)
		}
		if v := r.Header.Get("Sec-CH-UA-Platform"); v != "" {
			parts = append(parts, v)
		}
	}
	hash := sha256.Sum256([]byte(strings.Join(parts, "|")))
	return fmt.Sprintf("fp_%x", hash[:8])
}

func extractUsernameFromToken(token string) string {
	if strings.HasPrefix(token, "eyJ") {
		parts := strings.Split(token, ".")
		if len(parts) == 3 {
			payload, err := base64.RawURLEncoding.DecodeString(parts[1])
			if err == nil {
				var claims map[string]interface{}
				if err := json.Unmarshal(payload, &claims); err == nil {
					if sub, ok := claims["sub"].(string); ok {
						return sub
					}
				}
			}
		}
	}

	if user := extractMarzbanClassicSubUsername(token); user != "" {
		return user
	}

	for _, enc := range []func(string) ([]byte, error){base64.StdEncoding.DecodeString, base64.RawStdEncoding.DecodeString} {
		decoded, err := enc(token)
		if err != nil {
			continue
		}
		s := string(decoded)
		if idx := strings.Index(s, ","); idx > 0 {
			return strings.TrimSpace(s[:idx])
		}
		if len(s) > 0 && len(s) < 64 && !strings.Contains(s, ".") {
			return strings.TrimSpace(s)
		}
	}

	return ""
}

func extractMarzbanClassicSubUsername(token string) string {
	if len(token) < 11 {
		return ""
	}
	payload := token[:len(token)-10]
	padLen := (4 - len(payload)%4) % 4
	decoded, err := base64.RawURLEncoding.DecodeString(payload + strings.Repeat("=", padLen))
	if err != nil {
		decoded, err = base64.URLEncoding.DecodeString(payload + strings.Repeat("=", padLen))
		if err != nil {
			return ""
		}
	}
	s := string(decoded)
	if idx := strings.Index(s, ","); idx > 0 {
		return strings.TrimSpace(s[:idx])
	}
	return ""
}
