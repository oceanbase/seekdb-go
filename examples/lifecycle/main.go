// Run with: go run ./examples/lifecycle -db /path/to/database
package main

import (
	"errors"
	"flag"
	"fmt"
	"log"

	seekdb "github.com/oceanbase/seekdb-go"
)

func main() {
	dbDir := flag.String("db", "./data", "database directory to create or reopen")
	flag.Parse()
	if err := run(*dbDir); err != nil {
		log.Fatal(err)
	}
}

func run(dbDir string) (err error) {
	db, err := seekdb.Open(dbDir)
	if err != nil {
		return err
	}
	defer func() { err = errors.Join(err, db.Close()) }()

	endpoint, err := db.ConnectionOptions()
	if err != nil {
		return err
	}
	fmt.Printf("seekdb transport: %s\n", endpoint.Transport)
	// Use endpoint to configure a MySQL-protocol client. Close its connections
	// before returning, so they are released before the deferred db.Close.
	return nil
}
