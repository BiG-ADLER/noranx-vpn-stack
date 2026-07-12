package config

import "os"

type Config struct {
	Port       string
	MarzbanURL string
	DataDir    string
}

func Load() *Config {
	cfg := &Config{
		Port:       "3000",
		MarzbanURL: "http://127.0.0.1:8000",
		DataDir:    "/data",
	}

	if p := os.Getenv("PORT"); p != "" {
		cfg.Port = p
	}
	if u := os.Getenv("MARZBAN_URL"); u != "" {
		cfg.MarzbanURL = u
	}
	if d := os.Getenv("DATA_DIR"); d != "" {
		cfg.DataDir = d
	}
	return cfg
}
