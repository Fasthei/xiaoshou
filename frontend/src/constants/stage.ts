export const STAGE_META: Record<string, { label: string; color: string; emoji: string; bg: string }> = {
  lead:       { label: '商机池',    color: 'default', emoji: '🧊', bg: '#f5f5f5' },
  contacting: { label: '沟通中',    color: 'blue',    emoji: '📞', bg: '#e6f4ff' },
  active:     { label: '正式服务中', color: 'green',   emoji: '🎯', bg: '#f6ffed' },
  lost:       { label: '流失',      color: 'red',     emoji: '❌', bg: '#fff1f0' },
};

export const STAGE_ORDER = ['lead', 'contacting', 'active', 'lost'] as const;
export type StageKey = typeof STAGE_ORDER[number];
