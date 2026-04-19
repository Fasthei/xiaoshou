import { useEffect, useRef, useState } from 'react';
import {
  Button, Card, Collapse, Empty, List, Progress, Space, Spin, Tag, Timeline, Typography,
  message as antdMessage,
} from 'antd';
import {
  BulbOutlined, CaretRightOutlined, CloudOutlined, FileSearchOutlined, LinkOutlined,
  PlayCircleOutlined, ReloadOutlined, StopOutlined, ThunderboltOutlined,
} from '@ant-design/icons';
import {
  startInsightRun, fetchInsightFacts, fetchInsightRuns, fetchInsightRunFacts,
  type InsightEvent, type InsightFact, type InsightRun,
} from '../api/agents';

const { Text, Paragraph } = Typography;

const CATEGORY_META: Record<string, { label: string; color: string }> = {
  basic: { label: '基础信息', color: 'blue' },
  people: { label: '关键人', color: 'purple' },
  tech: { label: '技术栈', color: 'cyan' },
  news: { label: '近期动态', color: 'orange' },
  event: { label: '事件', color: 'magenta' },
  other: { label: '其他', color: 'default' },
};

interface StreamItem {
  ts: number;
  ev: InsightEvent;
}

function FactList({ facts }: { facts: InsightFact[] }) {
  if (facts.length === 0) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无事实" />;
  return (
    <List
      size="small"
      dataSource={facts}
      renderItem={(f) => {
        const meta = CATEGORY_META[f.category] || CATEGORY_META.other;
        return (
          <List.Item>
            <Space align="start">
              <Tag color={meta.color}>{meta.label}</Tag>
              <div>
                <div>{f.content}</div>
                {f.source_url && (
                  <a href={f.source_url} target="_blank" rel="noreferrer" style={{ fontSize: 11 }}>
                    <LinkOutlined /> 来源
                  </a>
                )}
              </div>
            </Space>
          </List.Item>
        );
      }}
    />
  );
}

function RunHistoryItem({
  customerId,
  run,
}: {
  customerId: number;
  run: InsightRun;
}) {
  const [expanded, setExpanded] = useState(false);
  const [facts, setFacts] = useState<InsightFact[] | null>(null);
  const [loading, setLoading] = useState(false);

  const toggleExpand = async () => {
    if (!expanded && facts === null) {
      setLoading(true);
      try {
        const fs = await fetchInsightRunFacts(customerId, run.id);
        setFacts(fs);
      } catch {
        setFacts([]);
      } finally {
        setLoading(false);
      }
    }
    setExpanded((v) => !v);
  };

  const statusColor = run.status === 'completed' ? 'green' : run.status === 'failed' ? 'red' : 'blue';
  const durationSec = run.duration_ms != null ? (run.duration_ms / 1000).toFixed(1) : null;
  const factCount = run.fact_count ?? 0;

  return (
    <div style={{ marginBottom: 8 }}>
      <Space wrap style={{ fontSize: 13 }}>
        <Tag color={statusColor}>{run.status}</Tag>
        <Text type="secondary">{new Date(run.started_at).toLocaleString()}</Text>
        {run.summary ? (
          <Text style={{ fontSize: 12 }} type="secondary">
            {run.summary.slice(0, 40)}
            {run.summary.length > 40 ? '…' : ''}
          </Text>
        ) : null}
        <Text type="secondary">{factCount} facts</Text>
        {durationSec && <Text type="secondary">耗时 {durationSec}s</Text>}
        <Button type="link" size="small" onClick={toggleExpand} style={{ padding: 0 }}>
          {expanded ? '收起' : '查看详情'}
        </Button>
      </Space>
      {expanded && (
        <div style={{ marginTop: 8, paddingLeft: 16 }}>
          {loading ? <Spin size="small" /> : <FactList facts={facts ?? []} />}
        </div>
      )}
    </div>
  );
}

export default function CustomerInsightPanel({ customerId }: { customerId: number }) {
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<{ done: number; total: number }>({ done: 0, total: 12 });
  const [stream, setStream] = useState<StreamItem[]>([]);
  const [summary, setSummary] = useState<string | null>(null);
  const [liveFacts, setLiveFacts] = useState<InsightFact[]>([]);
  const [latestFacts, setLatestFacts] = useState<InsightFact[] | null>(null);
  const [runs, setRuns] = useState<InsightRun[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const cancelRef = useRef<(() => void) | null>(null);

  const refreshHistory = async () => {
    setLoadingHistory(true);
    try {
      const rs = await fetchInsightRuns(customerId);
      setRuns(rs);
      // Fetch facts for the latest run to show in "最新结果"
      if (rs.length > 0) {
        const latestFacts = await fetchInsightRunFacts(customerId, rs[0].id);
        setLatestFacts(latestFacts);
      } else {
        setLatestFacts([]);
      }
    } catch {
      // silent
    } finally {
      setLoadingHistory(false);
    }
  };

  useEffect(() => {
    refreshHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customerId]);

  const start = () => {
    if (running) return;
    setRunning(true);
    setStream([]);
    setLiveFacts([]);
    setSummary(null);
    setProgress({ done: 0, total: 12 });

    cancelRef.current = startInsightRun(
      customerId,
      (ev) => {
        setStream((s) => [...s, { ts: Date.now(), ev }]);
        switch (ev.type) {
          case 'run_started':
            setProgress({ done: 0, total: ev.data.max_steps });
            break;
          case 'step_progress':
            setProgress({ done: ev.data.done, total: ev.data.total });
            break;
          case 'fact_recorded': {
            const f: InsightFact = {
              id: ev.data.id,
              category: ev.data.category,
              content: ev.data.content,
              source_url: ev.data.source_url,
              run_id: 0,
              discovered_at: new Date().toISOString(),
            };
            setLiveFacts((fs) => [...fs, f]);
            break;
          }
          case 'done':
            setSummary(ev.data.summary);
            setRunning(false);
            refreshHistory();
            break;
          case 'error':
            antdMessage.error(ev.data.message);
            setRunning(false);
            break;
        }
      },
      {
        onError: (err) => {
          antdMessage.error(`连接中断: ${err.message}`);
          setRunning(false);
          refreshHistory();
        },
        onComplete: () => {
          setRunning(false);
          refreshHistory();
        },
      },
    );
  };

  const stop = () => {
    cancelRef.current?.();
    cancelRef.current = null;
    setRunning(false);
  };

  const pct = Math.min(100, Math.round((progress.done / Math.max(1, progress.total)) * 100));
  const lastRun = runs[0];

  // While running, show live facts; after done, show facts from latest run
  const displayedLatestFacts = running ? liveFacts : (latestFacts ?? []);

  const collapseItems = [
    {
      key: 'latest',
      label: (
        <Space>
          <ThunderboltOutlined style={{ color: '#C19C00' }} />
          <Text strong>最新结果</Text>
          {lastRun && !running && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              {new Date(lastRun.started_at).toLocaleString()} · {displayedLatestFacts.length} facts
            </Text>
          )}
          {running && <Tag color="processing">运行中</Tag>}
        </Space>
      ),
      children: (
        <div>
          {running && (
            <Progress
              percent={pct}
              status="active"
              style={{ marginBottom: 12 }}
            />
          )}
          {summary && (
            <Card size="small" style={{ marginBottom: 12 }}>
              <Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0, fontSize: 13 }}>
                {summary}
              </Paragraph>
            </Card>
          )}
          {running && stream.length > 0 && (
            <Card
              size="small"
              title={<Space><FileSearchOutlined /> 执行流</Space>}
              bodyStyle={{ maxHeight: 260, overflowY: 'auto' }}
              style={{ marginBottom: 12 }}
            >
              <Timeline
                items={stream.slice(-30).map(({ ev, ts }) => ({
                  color: eventColor(ev.type),
                  children: (
                    <Space direction="vertical" size={2}>
                      <Text strong style={{ fontSize: 12 }}>
                        {eventLabel(ev.type)}
                        <Text type="secondary" style={{ marginLeft: 8, fontSize: 11 }}>
                          {new Date(ts).toLocaleTimeString()}
                        </Text>
                      </Text>
                      <Text style={{ fontSize: 12 }}>{describeEvent(ev)}</Text>
                    </Space>
                  ),
                }))}
              />
            </Card>
          )}
          {!running && displayedLatestFacts.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={'暂无洞察结果，点击 "运行新洞察" 开始'} />
          ) : (
            <FactList facts={displayedLatestFacts} />
          )}
        </div>
      ),
    },
    {
      key: 'history',
      label: (
        <Space>
          <CloudOutlined />
          <Text strong>历史洞察记录</Text>
          <Tag>{runs.length}</Tag>
        </Space>
      ),
      children: loadingHistory ? (
        <div style={{ textAlign: 'center', padding: 24 }}><Spin /></div>
      ) : runs.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无历史记录" />
      ) : (
        <Timeline
          style={{ marginTop: 8 }}
          items={runs.map((r) => ({
            color: r.status === 'completed' ? 'green' : r.status === 'failed' ? 'red' : 'blue',
            children: (
              <RunHistoryItem key={r.id} customerId={customerId} run={r} />
            ),
          }))}
        />
      ),
    },
  ];

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      {/* Header toolbar */}
      <Card size="small" styles={{ body: { padding: 12 } }}>
        <Space style={{ width: '100%', justifyContent: 'space-between' }} wrap>
          <Space direction="vertical" size={0}>
            <Text strong>
              <BulbOutlined style={{ color: '#C19C00' }} /> AI 客户洞察
            </Text>
            <Text type="secondary" style={{ fontSize: 12 }}>
              大模型自主规划调用 Jina 搜索 + LinkedIn 查询，广撒网收集客户周边信息（增量存档）
            </Text>
          </Space>
          <Space>
            <Button
              icon={<ReloadOutlined />}
              onClick={refreshHistory}
              loading={loadingHistory}
              disabled={running}
            >
              刷新
            </Button>
            {running ? (
              <Button icon={<StopOutlined />} danger onClick={stop}>中止</Button>
            ) : (
              <Button type="primary" icon={<PlayCircleOutlined />} onClick={start}>
                运行新洞察
              </Button>
            )}
          </Space>
        </Space>
      </Card>

      {/* Collapsible sections */}
      <Collapse
        defaultActiveKey={['latest']}
        expandIcon={({ isActive }) => (
          <CaretRightOutlined rotate={isActive ? 90 : 0} />
        )}
        items={collapseItems}
      />
    </Space>
  );
}

function eventColor(type: string): string {
  if (type === 'fact_recorded') return 'green';
  if (type === 'error' || type === 'tool_error') return 'red';
  if (type === 'finishing' || type === 'done') return 'blue';
  if (type === 'thinking') return 'gray';
  return 'cyan';
}

function eventLabel(type: string): string {
  return ({
    run_created: '已创建运行',
    run_started: '开始执行',
    step_progress: '进度',
    tool_call: '调用工具',
    tool_result: '工具结果',
    tool_error: '工具失败',
    thinking: '思考',
    fact_recorded: '记录事实',
    fact_skipped_duplicate: '跳过(重复)',
    finishing: '收尾',
    done: '完成',
    error: '错误',
  } as Record<string, string>)[type] || type;
}

function describeEvent(ev: InsightEvent): string {
  switch (ev.type) {
    case 'tool_call': return `${ev.data.name}(${summarizeArgs(ev.data.args)})`;
    case 'tool_result': return `${ev.data.name} → ${ev.data.preview?.slice(0, 180) || ''}`;
    case 'tool_error': return `${ev.data.name}: ${ev.data.error}`;
    case 'fact_recorded': return `[${ev.data.category}] ${ev.data.content}`;
    case 'fact_skipped_duplicate': return `[${ev.data.category}] ${ev.data.content} (已存在)`;
    case 'thinking': return ev.data.text;
    case 'step_progress': return `${ev.data.done}/${ev.data.total}`;
    case 'finishing': return ev.data.summary_preview;
    case 'done': return `总 ${ev.data.steps_done} 步`;
    case 'error': return ev.data.message;
    default: return '';
  }
}

function summarizeArgs(args: any): string {
  if (!args || typeof args !== 'object') return '';
  const entries = Object.entries(args).slice(0, 2);
  return entries.map(([k, v]) =>
    `${k}=${typeof v === 'string' ? `"${(v as string).slice(0, 60)}"` : JSON.stringify(v)}`
  ).join(', ');
}
