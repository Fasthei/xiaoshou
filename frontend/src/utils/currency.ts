/**
 * 货币符号查询。允许参数是 ISO 4217 代码 ('CNY' / 'USD' / ...) 或一个带
 * `currency` 字段的对象 (如 Allocation / Payment 行)。
 */

export const CURRENCY_SYMBOL: Record<string, string> = {
  CNY: '¥',
  USD: '$',
  HKD: 'HK$',
  EUR: '€',
  JPY: '¥',
  GBP: '£',
  SGD: 'S$',
};

export function currencySymbol(code?: string | null): string {
  if (!code) return '¥';
  return CURRENCY_SYMBOL[code.toUpperCase()] ?? code;
}

/** 从带 currency 字段的对象 (Allocation / Payment / ...) 取符号; 缺省 CNY。 */
export function currencySymOf(row?: { currency?: string | null } | null): string {
  return currencySymbol(row?.currency);
}
