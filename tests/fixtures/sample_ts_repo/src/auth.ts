export function parseToken(token: string) {
  return token.trim();
}

export async function verifyToken(token: string) {
  // token verification flow
  return parseToken(token);
}

export const loginHandler = async () => {
  // login route handler
  return verifyToken("session-token");
};

export class AuthService {
  verifyToken(token: string) {
    this.validate();
    return parseToken(token);
  }

  validate() {
    return true;
  }
}
