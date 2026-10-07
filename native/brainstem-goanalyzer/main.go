// brainstem-goanalyzer reads a JSON path list from stdin and emits Go AST
// import facts. It has no network, module-resolution, or project-execution
// behavior, so hosts can use it as an optional local semantic sidecar.
package main

import (
	"encoding/json"
	"fmt"
	"go/parser"
	"go/token"
	"io"
	"os"
	"strconv"
)

type request struct { Paths []string `json:"paths"` }
type fileResult struct { Path string `json:"path"`; Imports []string `json:"imports"`; Error string `json:"error,omitempty"` }
type response struct { Files []fileResult `json:"files"` }

func importsFor(path string) fileResult {
	parsed, err := parser.ParseFile(token.NewFileSet(), path, nil, parser.ImportsOnly)
	if err != nil { return fileResult{Path: path, Error: err.Error()} }
	imports := make([]string, 0, len(parsed.Imports))
	for _, spec := range parsed.Imports {
		value, err := strconv.Unquote(spec.Path.Value)
		if err != nil { return fileResult{Path: path, Error: fmt.Sprintf("invalid import literal: %v", err)} }
		imports = append(imports, value)
	}
	return fileResult{Path: path, Imports: imports}
}

func main() {
	input, err := io.ReadAll(os.Stdin); if err != nil { panic(err) }
	var payload request
	if err := json.Unmarshal(input, &payload); err != nil { panic(err) }
	output := response{Files: make([]fileResult, 0, len(payload.Paths))}
	for _, path := range payload.Paths { output.Files = append(output.Files, importsFor(path)) }
	if err := json.NewEncoder(os.Stdout).Encode(output); err != nil { panic(err) }
}
