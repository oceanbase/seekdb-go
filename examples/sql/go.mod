module github.com/oceanbase/seekdb-go/examples/sql

go 1.22

require (
	github.com/Microsoft/go-winio v0.6.2
	github.com/go-sql-driver/mysql v1.9.3
	github.com/oceanbase/seekdb-go v0.0.0-20261022060610-9823c6033562
)

require (
	filippo.io/edwards25519 v1.1.0 // indirect
	github.com/oceanbase/seekdb-go/native/darwin-arm64 v1.4.0 // indirect
	github.com/oceanbase/seekdb-go/native/linux-amd64 v1.4.0 // indirect
	github.com/oceanbase/seekdb-go/native/linux-arm64 v1.4.0 // indirect
	github.com/oceanbase/seekdb-go/native/windows-amd64 v1.4.0 // indirect
	golang.org/x/sys v0.10.0 // indirect
)

replace github.com/oceanbase/seekdb-go => ../..
