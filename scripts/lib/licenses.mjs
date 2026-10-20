// License policy evaluation. Pure functions so the policy itself can be tested.

const MISSING = new Set(["", "unknown", "unlicensed", "undefined", "none", "see license in license"]);

export function normalize(raw, aliases = {}) {
  if (Array.isArray(raw)) raw = raw.join(" OR ");
  const text = String(raw ?? "").trim();
  return aliases[text] ?? text;
}

function tokenize(expression) {
  return expression.match(/\(|\)|[^\s()]+/g) ?? [];
}

// Evaluates an SPDX-style expression: OR needs one allowed side, AND needs both.
// "WITH exception" suffixes are evaluated against the base license id.
export function isExpressionAllowed(expression, allowed) {
  const tokens = tokenize(expression);
  let pos = 0;

  function parsePrimary() {
    const token = tokens[pos++];
    if (token === "(") {
      const value = parseOr();
      if (tokens[pos++] !== ")") throw new Error(`Unbalanced parentheses in "${expression}"`);
      return value;
    }
    if (token === undefined || token === ")" || /^(AND|OR|WITH)$/i.test(token)) {
      throw new Error(`Unexpected token "${token}" in "${expression}"`);
    }
    if (tokens[pos]?.toUpperCase() === "WITH") pos += 2;
    return allowed.has(token.replace(/\+$/, ""));
  }
  function parseAnd() {
    let value = parsePrimary();
    while (tokens[pos]?.toUpperCase() === "AND") {
      pos++;
      const right = parsePrimary();
      value = value && right;
    }
    return value;
  }
  function parseOr() {
    let value = parseAnd();
    while (tokens[pos]?.toUpperCase() === "OR") {
      pos++;
      const right = parseAnd();
      value = value || right;
    }
    return value;
  }

  const result = parseOr();
  if (pos !== tokens.length) throw new Error(`Trailing tokens in "${expression}"`);
  return result;
}

function exceptionMatches(exception, ecosystem, name, license) {
  if (exception.ecosystem !== ecosystem || exception.license !== license) return false;
  return exception.package.endsWith("*")
    ? name.startsWith(exception.package.slice(0, -1))
    : exception.package === name;
}

// entries: [{ name, license }]. Returns { violations, excepted }.
export function evaluate(entries, policy, ecosystem) {
  const allowed = new Set(policy.allowed);
  const violations = [];
  const excepted = [];
  const isExcepted = (name, license) =>
    policy.exceptions.some((e) => exceptionMatches(e, ecosystem, name, license));

  for (const { name, license: rawLicense } of entries) {
    const license = normalize(rawLicense, policy.aliases);
    if (MISSING.has(license.toLowerCase())) {
      violations.push({ name, license: license || "(none)", problem: "missing license metadata" });
      continue;
    }
    let ok;
    try {
      ok = isExpressionAllowed(license, allowed);
    } catch {
      violations.push({ name, license, problem: "unparseable license expression" });
      continue;
    }
    if (ok) continue;
    if (isExcepted(name, license)) excepted.push({ name, license });
    else violations.push({ name, license, problem: "license not allowed by policy" });
  }
  return { violations, excepted };
}
