package main

import (
	"database/sql"
	"errors"
	"flag"
	"fmt"
	"log"
	"net"
	"time"

	"github.com/go-sql-driver/mysql"
	seekdb "github.com/oceanbase/seekdb-go"
)

func connect(db *seekdb.DB) (*sql.DB, error) {
	endpoint, err := db.ConnectionOptions()
	if err != nil {
		return nil, err
	}
	cfg := mysql.NewConfig()
	cfg.User = endpoint.User
	cfg.Timeout, cfg.ReadTimeout, cfg.WriteTimeout = 10*time.Second, 15*time.Second, 15*time.Second
	cfg.Params = map[string]string{"charset": "utf8mb4"}
	switch endpoint.Transport {
	case "unix_socket":
		cfg.Net, cfg.Addr = "unix", endpoint.UnixSocket
	case "tcp":
		cfg.Net, cfg.Addr = "tcp", net.JoinHostPort(endpoint.Host, fmt.Sprint(endpoint.Port))
	case "named_pipe":
		cfg.Net, cfg.Addr = "seekdb_pipe", endpoint.NamedPipe
	default:
		return nil, fmt.Errorf("unexpected transport %q", endpoint.Transport)
	}
	log.Printf("Connecting through %s", endpoint.Transport)
	client, err := sql.Open("mysql", cfg.FormatDSN())
	if err != nil {
		return nil, err
	}
	client.SetMaxOpenConns(1)
	return client, nil
}

func verify(dir string) (err error) {
	db, err := seekdb.Open(dir)
	if err != nil {
		return err
	}
	defer func() {
		if db != nil {
			err = errors.Join(err, db.Close())
		}
	}()
	client, err := connect(db)
	if err != nil {
		return err
	}
	defer func() {
		if client != nil {
			err = errors.Join(err, client.Close())
		}
	}()
	for _, statement := range []string{
		"CREATE DATABASE install_check CHARACTER SET utf8mb4",
		"CREATE TABLE install_check.records (id INT PRIMARY KEY, value VARCHAR(128))",
	} {
		if _, err := client.Exec(statement); err != nil {
			return err
		}
	}
	const expected = "seekdb 安装验证 🐬"
	if _, err := client.Exec("INSERT INTO install_check.records VALUES (?, ?)", 1, expected); err != nil {
		return err
	}
	if err := client.Close(); err != nil {
		return err
	}
	if err := db.Close(); err != nil {
		return err
	}
	db, err = seekdb.Open(dir)
	if err != nil {
		return err
	}
	client, err = connect(db)
	if err != nil {
		return err
	}
	var actual string
	if err := client.QueryRow("SELECT value FROM install_check.records WHERE id = ?", 1).Scan(&actual); err != nil {
		return err
	}
	if actual != expected {
		return fmt.Errorf("persisted value = %q, want %q", actual, expected)
	}
	log.Print("SQL and persistence passed")
	return nil
}

func main() {
	dir := flag.String("db", "database", "fresh database directory")
	flag.Parse()
	if err := verify(*dir); err != nil {
		log.Fatal(err)
	}
}
