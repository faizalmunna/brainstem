package com.example.auth;

public class AuthService {
    public boolean authenticateLoginRequest(String token) {
        return token != null && !token.isEmpty();
    }
}
