package main

import (
	"database/sql"
	"math"
	"os"
	"path/filepath"
	"runtime"
	"testing"
	"time"

	seekdb "github.com/oceanbase/seekdb-go"
)

func databaseDirectory(t *testing.T) string {
	t.Helper()
	base := os.Getenv("SEEKDB_TEST_ARTIFACT_DIR")
	if base != "" {
		if err := os.MkdirAll(base, 0700); err != nil {
			t.Fatal(err)
		}
	}
	root, err := os.MkdirTemp(base, "seekdb-"+t.Name()+"-")
	if err != nil {
		t.Fatal(err)
	}
	t.Logf("instance diagnostics: %s", root)
	t.Cleanup(func() {
		if t.Failed() {
			t.Logf("failed instance retained at %s", root)
			return
		}
		// Windows can hold a server log briefly after Close returns. Only
		// filesystem cleanup is retried; failed Open calls are never retried.
		deadline := time.Now().Add(5 * time.Second)
		for {
			err := os.RemoveAll(root)
			if err == nil {
				return
			}
			if runtime.GOOS != "windows" || time.Now().After(deadline) {
				t.Errorf("remove successful instance %s: %v", root, err)
				return
			}
			time.Sleep(100 * time.Millisecond)
		}
	})
	return filepath.Join(root, "database")
}

func sqlClient(t *testing.T, db *seekdb.DB) *sql.DB {
	t.Helper()
	client, err := connect(db)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := client.Close(); err != nil {
			t.Error(err)
		}
	})
	return client
}

func execSQL(t *testing.T, client *sql.DB, statement string, args ...any) {
	t.Helper()
	if _, err := client.Exec(statement, args...); err != nil {
		t.Fatalf("%s: %v", statement, err)
	}
}

func TestSQLLifecycle(t *testing.T) {
	dir := databaseDirectory(t)
	db, err := seekdb.Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := db.Close(); err != nil {
			t.Error(err)
		}
	})
	client := sqlClient(t, db)
	execSQL(t, client, "CREATE DATABASE integration_check CHARACTER SET utf8mb4")
	execSQL(t, client, "CREATE TABLE integration_check.records (id INT PRIMARY KEY, value VARCHAR(128))")
	const unicode = "seekdb 跨平台测试 🐬"
	statement, err := client.Prepare("INSERT INTO integration_check.records VALUES (?, ?)")
	if err != nil {
		t.Fatal(err)
	}
	defer statement.Close()
	if _, err := statement.Exec(1, unicode); err != nil {
		t.Fatal(err)
	}
	if err := statement.Close(); err != nil {
		t.Fatal(err)
	}
	var actual string
	if err := client.QueryRow("SELECT value FROM integration_check.records WHERE id = ?", 1).Scan(&actual); err != nil || actual != unicode {
		t.Fatalf("Unicode round trip = %q, %v", actual, err)
	}
	for _, commit := range []bool{false, true} {
		tx, err := client.Begin()
		if err != nil {
			t.Fatal(err)
		}
		defer tx.Rollback()
		id := 2
		if commit {
			id = 3
		}
		if _, err := tx.Exec("INSERT INTO integration_check.records VALUES (?, ?)", id, "transaction"); err != nil {
			t.Fatal(err)
		}
		if commit {
			err = tx.Commit()
		} else {
			err = tx.Rollback()
		}
		if err != nil {
			t.Fatal(err)
		}
	}
	execSQL(t, client, "UPDATE integration_check.records SET value = ? WHERE id = ?", "updated", 3)
	execSQL(t, client, "INSERT INTO integration_check.records VALUES (?, ?)", 4, "deleted")
	execSQL(t, client, "DELETE FROM integration_check.records WHERE id = ?", 4)
	execSQL(t, client, "CREATE TABLE integration_check.vectors (id INT PRIMARY KEY, embedding VECTOR(3))")
	execSQL(t, client, "INSERT INTO integration_check.vectors VALUES (1, '[1,2,3]'), (2, '[4,6,3]')")
	checkPersisted := func(client *sql.DB) {
		t.Helper()
		var count int
		if err := client.QueryRow("SELECT COUNT(*) FROM integration_check.records").Scan(&count); err != nil || count != 2 {
			t.Fatalf("record count after commit/rollback/delete = %d, %v", count, err)
		}
		for id, expected := range map[int]string{1: unicode, 3: "updated"} {
			if err := client.QueryRow("SELECT value FROM integration_check.records WHERE id = ?", id).Scan(&actual); err != nil || actual != expected {
				t.Fatalf("record %d = %q, want %q: %v", id, actual, expected, err)
			}
		}
		var distance float64
		if err := client.QueryRow("SELECT L2_DISTANCE(embedding, '[1,2,3]') FROM integration_check.vectors WHERE id = 2").Scan(&distance); err != nil || math.IsNaN(distance) || math.Abs(distance-5) > 1e-6 {
			t.Fatalf("vector distance = %g, want 5: %v", distance, err)
		}
	}
	checkPersisted(client)
	t.Log("prepared statements, Unicode, CRUD, commit/rollback and vector distance passed")

	// Two handles in this process refer to the same database. Closing one must
	// leave the other able to query through its own endpoint.
	second, err := seekdb.Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := second.Close(); err != nil {
			t.Error(err)
		}
	})
	if err := client.Close(); err != nil {
		t.Fatal(err)
	}
	if err := db.Close(); err != nil {
		t.Fatal(err)
	}
	secondClient := sqlClient(t, second)
	checkPersisted(secondClient)
	if err := secondClient.Close(); err != nil {
		t.Fatal(err)
	}
	if err := second.Close(); err != nil {
		t.Fatal(err)
	}
	t.Log("closing one of two handles leaves the other usable")

	reopened, err := seekdb.Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := reopened.Close(); err != nil {
			t.Error(err)
		}
	})
	checkPersisted(sqlClient(t, reopened))
	t.Log("SQL data, transaction effects and vectors survived a full close/reopen")
}
