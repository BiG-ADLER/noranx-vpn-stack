package proxy

import (
	"net/http"
	"testing"
)

func TestExtractUsernameFromToken(t *testing.T) {
	tests := []struct {
		name     string
		token    string
		expected string
	}{
		{
			name:     "classic marzban valtor",
			token:    "dmFsdG9yLDE3ODEyODI0NDkbwBPZoW8SB",
			expected: "valtor",
		},
		{
			name:     "simple base64 user1",
			token:    "dXNlcjE=",
			expected: "user1",
		},
		{
			name:     "health check style token",
			token:    "dGVzdF9oY184NjY4MiwxNzgxMjg2Njg1-x4EW6pZ8k",
			expected: "test_hc_86682",
		},
		{
			name:     "empty",
			token:    "",
			expected: "",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := extractUsernameFromToken(tt.token)
			if got != tt.expected {
				t.Fatalf("extractUsernameFromToken(%q) = %q, want %q", tt.token, got, tt.expected)
			}
		})
	}
}

func TestExtractSubToken(t *testing.T) {
	tests := []struct {
		path     string
		expected string
	}{
		{"/sub/abc123", "abc123"},
		{"/sub/abc123/clash", "abc123"},
		{"/sub/abc123/v2ray", "abc123"},
		{"/sub/abc123/", "abc123"},
	}

	for _, tt := range tests {
		got := extractSubToken(tt.path)
		if got != tt.expected {
			t.Fatalf("extractSubToken(%q) = %q, want %q", tt.path, got, tt.expected)
		}
	}
}

func TestBuildFallbackFingerprint(t *testing.T) {
	token := "testtoken"
	ua := "v2rayN/7.0"

	req1 := httptestRequestWithHeaders(map[string]string{
		"User-Agent": ua,
		"X-Real-IP":  "10.0.0.1",
	})
	req2 := httptestRequestWithHeaders(map[string]string{
		"User-Agent": ua,
		"X-Real-IP":  "10.0.0.2",
	})
	reqSame := httptestRequestWithHeaders(map[string]string{
		"User-Agent": ua,
		"X-Real-IP":  "10.0.0.1",
	})

	fp1 := buildFallbackFingerprint(req1, token, ua)
	fp2 := buildFallbackFingerprint(req2, token, ua)
	fpSame := buildFallbackFingerprint(reqSame, token, ua)

	if fp1 != fp2 {
		t.Fatalf("VPN client fingerprint should ignore IP, got %q vs %q", fp1, fp2)
	}
	if fp1 != fpSame {
		t.Fatalf("expected same fingerprint for same inputs, got %q vs %q", fp1, fpSame)
	}

	browserUA := "Mozilla/5.0 (Linux; Android 10) Chrome/120.0 Mobile"
	reqB1 := httptestRequestWithHeaders(map[string]string{
		"User-Agent": browserUA,
		"X-Real-IP":  "10.0.0.1",
	})
	reqB2 := httptestRequestWithHeaders(map[string]string{
		"User-Agent": browserUA,
		"X-Real-IP":  "10.0.0.2",
	})
	fpB1 := buildFallbackFingerprint(reqB1, token, browserUA)
	fpB2 := buildFallbackFingerprint(reqB2, token, browserUA)
	if fpB1 == fpB2 {
		t.Fatalf("non-VPN fingerprint should differ by IP, got same %q", fpB1)
	}
}

func TestShouldCountDevice(t *testing.T) {
	tests := []struct {
		ua   string
		want bool
	}{
		{"TelegramBot (like TwitterBot)", false},
		{"Mozilla/5.0 (Linux; Android 10) Chrome/120.0 Mobile Safari/537.36", false},
		{"v2rayNG/2.2.4", true},
		{"v2rayN/7.0", true},
		{"HiddifyNext/1.0", true},
		{"curl/8.0", false},
		{"", false},
	}
	for _, tt := range tests {
		got := shouldCountDevice(tt.ua)
		if got != tt.want {
			t.Fatalf("shouldCountDevice(%q) = %v, want %v", tt.ua, got, tt.want)
		}
	}
}

func httptestRequestWithHeaders(headers map[string]string) *http.Request {
	req, _ := http.NewRequest(http.MethodGet, "http://127.0.0.1/sub/token", nil)
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	return req
}
