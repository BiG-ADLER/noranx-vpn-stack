package db

import (
	"database/sql"
	"os"
	"path/filepath"

	"github.com/kets/qentvpn/marzban-device-limit/internal/model"
	_ "modernc.org/sqlite"
)

var DB *sql.DB

func Init(dataDir string) error {
	if err := os.MkdirAll(dataDir, 0755); err != nil {
		return err
	}

	dbPath := filepath.Join(dataDir, "device_limit.db")
	var err error
	DB, err = sql.Open("sqlite", dbPath)
	if err != nil {
		return err
	}

	return initSchema()
}

func initSchema() error {
	query := `
    CREATE TABLE IF NOT EXISTS devices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        hwid TEXT,
        user_agent TEXT,
        fingerprint TEXT NOT NULL,
        last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
        first_seen DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE UNIQUE INDEX IF NOT EXISTS idx_devices_user_fp ON devices(username, fingerprint);
    
    CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        device_limit INTEGER DEFAULT 3,
        hwid_enabled BOOLEAN DEFAULT 1
    );
    `
	_, err := DB.Exec(query)
	return err
}

func GetDeviceCount(username string) (int, error) {
	var count int
	err := DB.QueryRow("SELECT COUNT(*) FROM devices WHERE username = ?", username).Scan(&count)
	return count, err
}

func TrackDevice(d model.Device) error {
	query := `INSERT INTO devices (username, hwid, user_agent, fingerprint, last_seen) 
             VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
             ON CONFLICT(username, fingerprint) DO UPDATE SET 
             last_seen=CURRENT_TIMESTAMP, user_agent=excluded.user_agent, hwid=excluded.hwid`

	_, err := DB.Exec(query, d.Username, d.HWID, d.UserAgent, d.Fingerprint)
	return err
}

func GetUserLimit(username string) (model.UserConfig, error) {
	var config model.UserConfig
	config.Username = username

	err := DB.QueryRow(
		"SELECT device_limit, hwid_enabled FROM users WHERE username = ?",
		username,
	).Scan(&config.DeviceLimit, &config.HWIDEnabled)
	if err == sql.ErrNoRows {
		config.Configured = false
		config.HWIDEnabled = false
		return config, nil
	}
	if err != nil {
		return config, err
	}
	config.Configured = true
	return config, err
}

func GetAllDevices(username string) ([]model.Device, error) {
	rows, err := DB.Query("SELECT id, username, hwid, user_agent, fingerprint, last_seen FROM devices WHERE username = ?", username)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var devices []model.Device
	for rows.Next() {
		var d model.Device
		if err := rows.Scan(&d.ID, &d.Username, &d.HWID, &d.UserAgent, &d.Fingerprint, &d.LastSeen); err != nil {
			return nil, err
		}
		devices = append(devices, d)
	}
	if devices == nil {
		devices = []model.Device{}
	}
	return devices, nil
}

func DeleteDevice(username string, id int64) error {
	_, err := DB.Exec("DELETE FROM devices WHERE username = ? AND id = ?", username, id)
	return err
}

func ClearDevices(username string) error {
	_, err := DB.Exec("DELETE FROM devices WHERE username = ?", username)
	return err
}

func UpdateUserLimit(config model.UserConfig) error {
    query := `INSERT INTO users (username, device_limit, hwid_enabled) 
              VALUES (?, ?, ?)
              ON CONFLICT(username) DO UPDATE SET 
              device_limit=excluded.device_limit, hwid_enabled=excluded.hwid_enabled`
    _, err := DB.Exec(query, config.Username, config.DeviceLimit, config.HWIDEnabled)
    return err
}
