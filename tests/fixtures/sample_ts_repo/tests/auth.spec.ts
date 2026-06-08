import { verifyToken } from "../src/auth";

export const authSpec = async () => {
  return verifyToken("abc");
};
