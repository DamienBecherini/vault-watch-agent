// The one export of the IA on-prem guide's scripts/lib/vault-walk.mjs that audit-watchlist-quotes.mjs reads:
// the guide's root, two folders above this file (scripts/lib/).
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const VAULT_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
