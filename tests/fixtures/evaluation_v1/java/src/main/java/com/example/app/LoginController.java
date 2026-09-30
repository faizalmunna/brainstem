package com.example.app;

import com.example.auth.AuthService;

public class LoginController {
    private final AuthService service = new AuthService();

    public boolean login(String token) {
        return service.authenticateLoginRequest(token);
    }
}
