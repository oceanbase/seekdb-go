// Package seekdb manages a local seekdb server through the bundled libseekdb
// lifecycle API. Open a DB, configure a caller-owned MySQL-protocol client with
// its ConnectionOptions, and close all client connections before closing the DB.
//
// Building requires Go 1.22 or later, cgo, a C compiler, and a supported native
// platform. The matching runtime is embedded at build time and extracted to the
// user cache on first use; Open does not download files.
package seekdb
