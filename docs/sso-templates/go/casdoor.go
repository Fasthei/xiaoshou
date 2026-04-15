// Casdoor JWT verification — Go
//
// go get github.com/golang-jwt/jwt/v5
//
// Use for cloud management system (云管) or any non-Python/TS service.

package auth

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

type Config struct {
	Endpoint     string
	Org          string
	AppName      string
	ClientID     string
	ClientSecret string
	RedirectURI  string
	CertPEM      string // optional, else fetched from Casdoor
}

type Claims struct {
	Name  string   `json:"name"`
	Email string   `json:"email"`
	Owner string   `json:"owner"`
	Roles []string `json:"roles"` // Casdoor may send []string OR []Role{}; normalize at marshal time
	jwt.RegisteredClaims
}

var (
	pemCache string
	pemOnce  sync.Once
	pemErr   error
)

func loadPem(cfg Config) (string, error) {
	pemOnce.Do(func() {
		if strings.Contains(cfg.CertPEM, "BEGIN") {
			pemCache = strings.ReplaceAll(cfg.CertPEM, "\\n", "\n")
			return
		}
		u := strings.TrimRight(cfg.Endpoint, "/") + "/api/get-cert?id=" + url.QueryEscape(cfg.Org+"/"+cfg.AppName)
		client := &http.Client{Timeout: 10 * time.Second}
		resp, err := client.Get(u)
		if err != nil {
			pemErr = err
			return
		}
		defer resp.Body.Close()
		var data struct {
			Data struct {
				Certificate string `json:"certificate"`
			} `json:"data"`
			Certificate string `json:"certificate"`
		}
		if err := json.NewDecoder(resp.Body).Decode(&data); err != nil {
			pemErr = err
			return
		}
		cert := data.Data.Certificate
		if cert == "" {
			cert = data.Certificate
		}
		if cert == "" {
			pemErr = errors.New("empty cert from casdoor")
			return
		}
		pemCache = cert
	})
	return pemCache, pemErr
}

// VerifyToken validates a Casdoor-issued JWT and returns typed claims.
func VerifyToken(tokenStr string, cfg Config) (*Claims, error) {
	pem, err := loadPem(cfg)
	if err != nil {
		return nil, fmt.Errorf("load pem: %w", err)
	}
	key, err := jwt.ParseRSAPublicKeyFromPEM([]byte(pem))
	if err != nil {
		return nil, fmt.Errorf("parse pem: %w", err)
	}

	tok, err := jwt.ParseWithClaims(tokenStr, &Claims{}, func(t *jwt.Token) (interface{}, error) {
		if t.Method.Alg() != "RS256" {
			return nil, fmt.Errorf("unexpected alg: %v", t.Header["alg"])
		}
		return key, nil
	},
		jwt.WithAudience(cfg.ClientID),
		jwt.WithIssuer(strings.TrimRight(cfg.Endpoint, "/")),
	)
	if err != nil {
		return nil, err
	}
	if !tok.Valid {
		return nil, errors.New("invalid token")
	}
	c, _ := tok.Claims.(*Claims)
	return c, nil
}

// HasRole reports whether the claims include any of the required roles.
func (c *Claims) HasRole(roles ...string) bool {
	for _, r := range c.Roles {
		for _, want := range roles {
			if r == want {
				return true
			}
		}
	}
	return false
}
