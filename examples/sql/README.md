# SQL and persistence example

This executable opens seekdb, obtains its endpoint, configures a MySQL protocol
client, writes parameterized Unicode data, and checks that data after a full
close/reopen. It can be rerun against the same directory. It creates an
`install_check` database and updates row 1 in `install_check.records`.

With the [platform prerequisites](../../README.md#install) installed, run from
this directory:

```sh
go run -mod=readonly . -db ../../sql-example-data
```

The example's `go.mod` uses a relative `replace` to test the SDK in this checkout.
To use the example in an independent application, copy `main.go` and
`pipe_windows.go` into an empty directory, then run:

```sh
go mod init example.com/seekdb-demo
go get github.com/oceanbase/seekdb-go@latest github.com/go-sql-driver/mysql@v1.9.3 github.com/Microsoft/go-winio@v0.6.2
go run . -db ./data
```

Use a specific root SDK version instead of `@latest` when pinning an application.
The `_windows.go` filename limits the named-pipe adapter to Windows builds.
Current Windows bundles return TCP; the adapter is provided for a runtime that
explicitly returns `named_pipe` and is not exercised by the current bundle.

Always derive the transport and address from `ConnectionOptions`. Close SQL
clients before their lifecycle handles. `DB.Close` manages the server lifetime;
it is separate from `database/sql.DB.Close`.

The integration test in this module also checks transactions, vector distance,
two handles to the same database and persistence:

```sh
go test -mod=readonly -count=1 -v -timeout 10m .
```

Each test creates a fresh database. Failed instances are retained and their
location is printed; successful instances are removed. Set
`SEEKDB_TEST_ARTIFACT_DIR` to choose the parent directory for those instances.
