/**
 * 视觉 token — Azure Portal 克制风，企业后台统一色彩中枢。
 *
 * 改颜色只改这一个文件。组件里禁止写死新 hex。
 * 仅颜色 / 阴影 / 圆角，不管布局 / 间距骨架。
 */

export const COLORS = {
  // 主色 (Azure Blue)
  primary: '#0078D4',
  primaryHover: '#106EBE',
  primaryActive: '#005A9E',
  primarySoft: '#DEECF9',   // 浅蓝底，用于 hover 行 / selected tag 背景

  // 中性文字
  text: '#1F2937',          // 一级文字
  textSecondary: '#6B7280', // 二级文字
  textDisabled: '#A6A6A6',

  // 面板与分割
  bgPage: '#F5F7FA',        // 页面背景
  bgCard: '#FFFFFF',        // 卡片 / 抽屉背景
  bgSubtle: '#FAFAFA',      // 次级底色 (表格条纹、hover)
  border: '#E1DFDD',        // 边框 / 分割线
  borderStrong: '#C8C6C4',

  // 语义色 (Fluent 风格，克制的饱和)
  success: '#107C10',
  warning: '#C19C00',
  danger: '#A4262C',
  info: '#0078D4',

  // 图表调色板 (主色 + 克制的互补色)
  chart: {
    azure: '#0078D4',
    aws: '#8C5A00',     // 克制琥珀
    gcp: '#A4262C',     // 克制红
    aliyun: '#107C10',  // 克制绿
    unknown: '#8A8886',

    // 订单/资源状态
    available: '#107C10',
    allocated: '#0078D4',
    standby: '#A19F9D',
    expired: '#C8C6C4',
    frozen: '#A4262C',
    exhausted: '#8C5A00',
  },

  // Stage 颜色 (lifecycle)
  stage: {
    lead: '#A19F9D',
    contacting: '#2B88D8',
    active: '#107C10',
    lost: '#A4262C',
  },
} as const;

/** 标准阴影层级 —— 不再有厚重发光。 */
export const ELEVATION = {
  none: 'none',
  card: '0 1px 2px rgba(0, 0, 0, 0.04), 0 1px 2px rgba(0, 0, 0, 0.06)',
  raised: '0 2px 4px rgba(0, 0, 0, 0.06), 0 1px 2px rgba(0, 0, 0, 0.08)',
} as const;

/** antd theme token 对象，供 App.tsx 的 ConfigProvider 使用。 */
export const ANTD_TOKEN = {
  colorPrimary: COLORS.primary,
  colorPrimaryHover: COLORS.primaryHover,
  colorPrimaryActive: COLORS.primaryActive,
  colorInfo: COLORS.info,
  colorSuccess: COLORS.success,
  colorWarning: COLORS.warning,
  colorError: COLORS.danger,
  colorText: COLORS.text,
  colorTextSecondary: COLORS.textSecondary,
  colorBorder: COLORS.border,
  colorBorderSecondary: COLORS.border,
  colorBgLayout: COLORS.bgPage,
  colorBgContainer: COLORS.bgCard,
  borderRadius: 4,       // Azure Portal 是 2px，这里用 4px 兼顾可读
  borderRadiusLG: 6,
  wireframe: false,
} as const;

/** antd 组件级覆盖，统一选中态 / 菜单 / Tag 等。 */
export const ANTD_COMPONENTS = {
  Button: {
    primaryShadow: 'none',
    defaultShadow: 'none',
    borderRadius: 4,
  },
  Card: {
    boxShadow: ELEVATION.card,
    boxShadowTertiary: ELEVATION.card,
  },
  Menu: {
    itemSelectedBg: COLORS.primarySoft,
    itemSelectedColor: COLORS.primary,
    itemActiveBg: COLORS.primarySoft,
  },
  Tabs: {
    itemSelectedColor: COLORS.primary,
    itemHoverColor: COLORS.primaryHover,
    inkBarColor: COLORS.primary,
  },
  Tag: {
    defaultBg: COLORS.bgSubtle,
    defaultColor: COLORS.textSecondary,
  },
  Table: {
    headerBg: COLORS.bgSubtle,
    headerColor: COLORS.textSecondary,
    rowHoverBg: COLORS.primarySoft,
  },
  Progress: {
    defaultColor: COLORS.primary,
  },
  Statistic: {
    titleFontSize: 13,
    contentFontSize: 22,
  },
} as const;
