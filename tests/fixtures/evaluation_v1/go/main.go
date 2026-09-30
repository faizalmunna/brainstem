package main

import "example.com/brainstem-evaluation/go/internal/auth"

func main() {
	_ = auth.CheckAuthenticationToken("demo")
}
