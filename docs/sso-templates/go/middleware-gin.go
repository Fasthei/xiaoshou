// Gin middleware using the auth.VerifyToken above.
package auth

import (
	"net/http"
	"os"
	"strings"

	"github.com/gin-gonic/gin"
)

const CtxUserKey = "casdoor.user"

func RequireAuth(cfg Config) gin.HandlerFunc {
	return func(c *gin.Context) {
		if os.Getenv("AUTH_ENABLED") == "false" {
			c.Set(CtxUserKey, &Claims{Name: "dev", Roles: []string{"admin"}})
			c.Next()
			return
		}
		h := c.GetHeader("Authorization")
		if !strings.HasPrefix(h, "Bearer ") {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "missing bearer token"})
			return
		}
		claims, err := VerifyToken(strings.TrimPrefix(h, "Bearer "), cfg)
		if err != nil {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "invalid token", "detail": err.Error()})
			return
		}
		c.Set(CtxUserKey, claims)
		c.Next()
	}
}

func RequireRoles(cfg Config, roles ...string) gin.HandlerFunc {
	auth := RequireAuth(cfg)
	return func(c *gin.Context) {
		auth(c)
		if c.IsAborted() {
			return
		}
		u, _ := c.Get(CtxUserKey)
		claims := u.(*Claims)
		if !claims.HasRole(roles...) {
			c.AbortWithStatusJSON(http.StatusForbidden, gin.H{"error": "insufficient role"})
			return
		}
		c.Next()
	}
}
