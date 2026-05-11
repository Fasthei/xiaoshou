/**
 * 全系统时间显示统一走 UTC+8 (Asia/Shanghai)。
 *
 * 后端返回的 datetime 多为 naive ISO 字符串 (服务端可能在 UTC 或本地 TZ),
 * 浏览器默认按 LOCAL TZ 解析, 在多时区/容器环境下展示会偏 8 小时。
 *
 * 这里统一: 把后端 ISO 字符串视作 UTC 解析, 再投影到 Asia/Shanghai 显示。
 * 副作用: 已经在 main.tsx 加载本文件后, 任何 dayjs(...).tz() 都走 Asia/Shanghai。
 */
import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';
import timezone from 'dayjs/plugin/timezone';

dayjs.extend(utc);
dayjs.extend(timezone);

export const APP_TZ = 'Asia/Shanghai';
dayjs.tz.setDefault(APP_TZ);

/** 把后端 ISO 字符串当作 UTC 解析, 投影到 UTC+8 后格式化。 */
export function fmtTime(
  iso: string | null | undefined,
  pattern: string = 'YYYY-MM-DD HH:mm:ss',
): string {
  if (!iso) return '—';
  return dayjs.utc(iso).tz(APP_TZ).format(pattern);
}

/** 同上, 但只到分钟 (列表展示用)。 */
export function fmtTimeShort(iso: string | null | undefined): string {
  return fmtTime(iso, 'YYYY-MM-DD HH:mm');
}

/** 日期 (YYYY-MM-DD)。已经是 YYYY-MM-DD 的字符串原样返回, 避免 UTC 转换把日子推前。 */
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) return iso;
  return dayjs.utc(iso).tz(APP_TZ).format('YYYY-MM-DD');
}
