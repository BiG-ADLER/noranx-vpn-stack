# Build Stage
FROM golang:1.22-alpine AS builder

WORKDIR /app

# Install git and tzdata (so we can copy zoneinfo later)
RUN apk add --no-cache git tzdata

COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN go build -o device-limit cmd/device-limit/main.go

# Final Stage
FROM alpine:latest

WORKDIR /app
COPY --from=builder /app/device-limit .
COPY --from=builder /usr/share/zoneinfo /usr/share/zoneinfo
RUN mkdir -p /data

EXPOSE 3000

CMD ["./device-limit"]
