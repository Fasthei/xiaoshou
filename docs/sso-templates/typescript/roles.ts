// Shared role constants — mirrors docs/ROLES.md.
// Keep this identical in every TS system (gongdan / opscenter / ...).

export const Roles = {
  ADMIN: 'admin',
  SALES: 'sales',
  SALES_MANAGER: 'sales_manager',
  OPS: 'ops',
  OPS_MANAGER: 'ops_manager',
  FINANCE: 'finance',
  SUPPORT: 'support',
  AUDITOR: 'auditor',
  READONLY: 'readonly',
} as const;

export type Role = (typeof Roles)[keyof typeof Roles];

export const WRITE_ROLES: Role[] = [Roles.ADMIN, Roles.SALES, Roles.SALES_MANAGER, Roles.OPS, Roles.OPS_MANAGER];
export const MANAGER_ROLES: Role[] = [Roles.ADMIN, Roles.SALES_MANAGER, Roles.OPS_MANAGER];
