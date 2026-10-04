// Money arrives as exact decimal text ("61.05", "-24.50", "0.000901"). This is the one place
// that formats it. It never becomes a float, so no cents can be lost.
const MONEY = /^(-?)(\d+)(?:\.(\d+))?$/;

function parts(text: string): [sign: string, whole: string, frac: string | undefined] {
  const match = MONEY.exec(text);
  if (!match) throw new Error(`Not a money amount: ${JSON.stringify(text)}`);
  return [match[1], match[2], match[3]];
}

/** "1234.50" becomes "$1,234.50". Keeps every decimal place the engine wrote. */
export function formatMoney(text: string): string {
  const [sign, whole, frac] = parts(text);
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `${sign}$${grouped}${frac === undefined ? "" : `.${frac}`}`;
}

/** Adds amounts exactly in whole cents (or smaller units), returning decimal text. */
export function sumMoney(texts: string[]): string {
  const scale = Math.max(2, ...texts.map((text) => parts(text)[2]?.length ?? 0));
  let total = BigInt(0);
  for (const text of texts) {
    const [sign, whole, frac] = parts(text);
    const units = BigInt(whole + (frac ?? "").padEnd(scale, "0"));
    total += sign ? -units : units;
  }
  const negative = total < BigInt(0);
  const digits = (negative ? -total : total).toString().padStart(scale + 1, "0");
  return `${negative ? "-" : ""}${digits.slice(0, -scale)}.${digits.slice(-scale)}`;
}
