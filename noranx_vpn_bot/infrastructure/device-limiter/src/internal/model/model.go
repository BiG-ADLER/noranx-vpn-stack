package model

import "time"

type Device struct {
	ID          int64     `json:"id"`
	Username    string    `json:"username"`
	HWID        string    `json:"hwid"`
	UserAgent   string    `json:"user_agent"`
	Fingerprint string    `json:"fingerprint"`
	LastSeen    time.Time `json:"last_seen"`
	FirstSeen   time.Time `json:"first_seen"` // Optional, if schema supports it
}

type UserConfig struct {
	Username    string `json:"username"`
	DeviceLimit int    `json:"device_limit"`
	HWIDEnabled bool   `json:"hwid_enabled"`
	Configured  bool   `json:"configured"`
}

// LimitUpdateRequest is the PUT /api/limit body.
type LimitUpdateRequest struct {
	Username     string `json:"username"`
	DeviceLimit  int    `json:"device_limit"`
	HWIDEnabled  bool   `json:"hwid_enabled"`
	ClearDevices bool   `json:"clear_devices"`
}
