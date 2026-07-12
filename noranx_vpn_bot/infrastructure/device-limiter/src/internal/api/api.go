package api

import (
	"encoding/json"
	"net/http"
	"strconv"

	"github.com/kets/qentvpn/marzban-device-limit/internal/db"
	"github.com/kets/qentvpn/marzban-device-limit/internal/model"
)

func RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("/api/devices", handleDevices)
	mux.HandleFunc("/api/devices/clear", handleClearDevices)
	mux.HandleFunc("/api/device/delete", handleDeleteDevice)
	mux.HandleFunc("/api/limit", handleLimit)
}

func handleDevices(w http.ResponseWriter, r *http.Request) {
	username := r.URL.Query().Get("username")
	if username == "" {
		http.Error(w, "username required", http.StatusBadRequest)
		return
	}

	devices, err := db.GetAllDevices(username)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(devices)
}

func handleDeleteDevice(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodDelete {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	username := r.URL.Query().Get("username")
	idStr := r.URL.Query().Get("id")

	if username == "" || idStr == "" {
		http.Error(w, "username and id required", http.StatusBadRequest)
		return
	}

	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil {
		http.Error(w, "invalid id", http.StatusBadRequest)
		return
	}

	if err := db.DeleteDevice(username, id); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(map[string]string{"status": "deleted"})
}

func handleClearDevices(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodDelete {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	username := r.URL.Query().Get("username")
	if username == "" {
		http.Error(w, "username required", http.StatusBadRequest)
		return
	}

	if err := db.ClearDevices(username); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(map[string]string{"status": "cleared"})
}

func handleLimit(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodGet {
		username := r.URL.Query().Get("username")
		if username == "" {
			http.Error(w, "username required", http.StatusBadRequest)
			return
		}

		limit, err := db.GetUserLimit(username)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(limit)
		return
	}

	if r.Method == http.MethodPut {
		var req model.LimitUpdateRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		if req.Username == "" {
			http.Error(w, "username required", http.StatusBadRequest)
			return
		}

		if req.ClearDevices {
			if err := db.ClearDevices(req.Username); err != nil {
				http.Error(w, err.Error(), http.StatusInternalServerError)
				return
			}
		}

		config := model.UserConfig{
			Username:    req.Username,
			DeviceLimit: req.DeviceLimit,
			HWIDEnabled: req.HWIDEnabled,
		}
		if err := db.UpdateUserLimit(config); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}

		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(map[string]string{"status": "updated"})
		return
	}

	http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
}
