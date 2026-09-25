package auth

func CheckAuthenticationToken(token string) bool {
	return token != ""
}
