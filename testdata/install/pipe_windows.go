package main

import (
	"context"
	"net"

	"github.com/Microsoft/go-winio"
	"github.com/go-sql-driver/mysql"
)

func init() {
	mysql.RegisterDialContext("seekdb_pipe", func(ctx context.Context, address string) (net.Conn, error) {
		return winio.DialPipeContext(ctx, address)
	})
}
