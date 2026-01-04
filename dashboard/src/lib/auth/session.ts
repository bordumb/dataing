import { getCurrentUser } from "@/lib/api/users";

export async function getSession() {
  const user = await getCurrentUser();
  return { user };
}
