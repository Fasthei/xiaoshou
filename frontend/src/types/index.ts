export interface Pagination<T> {
  total: number;
  items: T[];
}

export interface Customer {
  id: number;
  customer_code: string;
  customer_name: string;
  customer_short_name?: string | null;
  industry?: string | null;
  region?: string | null;
  customer_level?: string | null;
  customer_status: string;
  sales_user_id?: number | null;
  operation_user_id?: number | null;
  current_resource_count?: number;
  current_month_consumption?: string | number;
  next_month_forecast?: string | number | null;
  source_system?: string | null;
  source_id?: string | null;
  employee_size?: number | null;
  annual_revenue?: string | number | null;
  last_meeting_at?: string | null;
  last_follow_time?: string | null;
  trade_count?: number | null;
  website?: string | null;
  linkedin_url?: string | null;
  note?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface Resource {
  id: number;
  resource_code: string;
  resource_type: string;
  cloud_provider?: string | null;
  account_name?: string | null;
  total_quantity?: number | null;
  allocated_quantity?: number;
  available_quantity?: number | null;
  unit_cost?: string | number | null;
  suggested_price?: string | number | null;
  resource_status: string;
  created_at?: string;
}

export interface Allocation {
  id: number;
  allocation_code: string;
  customer_id: number;
  resource_id: number;
  allocated_quantity: number;
  unit_cost?: string | number | null;
  unit_price?: string | number | null;
  total_cost?: string | number | null;
  total_price?: string | number | null;
  profit_amount?: string | number | null;
  profit_rate?: string | number | null;
  allocation_status: string;
  created_at?: string;
}

export interface UsageRecord {
  id: number;
  customer_id: number;
  resource_id: number;
  usage_date: string;
  usage_amount: string | number;
  usage_unit?: string | null;
  cost?: string | number | null;
}
