import { useEffect, useRef, useState } from 'react';
import {
  Button, Card, Empty, List, Progress, Space, Tabs, Tag, Timeline, Typography,
  message as antdMessage,
} from 'antd';
import {
  BulbOutlined, CloudOutlined, FileSearchOutlined, LinkOutlined,
  PlayCircleOutlined, StopOutlined, ThunderboltOutlined,
} from '@ant-design/icons';
import {
  startInsightRun, fetchInsightFacts, fetchInsightRuns,
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

export default function CustomerInsightPanel({ customerId }: { customerId: number }) {
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<{ done: number; total: number }>({ done: 0, total: 12 });
  const [stream, setStream] = useState<StreamItem[]>([]);
  const [summary, setSummary] = useState<string | null>(null);
  const [liveFacts, setLiveFacts] = useState<InsightFact[]>([]);
  const [historyFacts, setHistoryFacts] = useState<InsightFact[]>([]);
  const [runs, setRuns] = useState<InsightRun[]>([]);
  const cancelRef = useRef<(() => void) | null>(null);

  const refreshHistory = async () => {
    try {
      const [rs, fs] = await Promise.all([
        fetchInsightRuns(customerId),
        fetchInsightFacts(customerId),
      ]);
      setRuns(rs);
      setHistoryFacts(fs);
    } catch (e) {
      // silent — probably 401 or 404 on fresh install
    }
  };

  useEffect(() => { refreshHistory(); /* eslint-disable-next-line */ }, [customerId]);

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
              id: ev.data.id, category: ev.data.category, content: ev.data.content,
              source_url: ev.data.source_url, run_id: 0, discovered_at: new Date().toISOString(),
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
        onError: (err) => { antdMessage.error(`连接中断: ${err.message}`); setRunning(false); },
        onComplete: () => { setRunning(false); },
      },
    );
  };

  const stop = () => {
    cancelRef.current?.();
    cancelRef.current = null;
    setRunning(false);
  };

  const pct = Math.min(100, Math.round((progress.done / Math.max(1, progress.total)) * 100));

  const groupByCategory = (facts: InsightFact[]) => {
    const g: Record<string, InsightFact[]> = {};
    for (const f of facts) (g[f.category] ||= []).push(f);
    return g;
  };

  const factsByCat = groupByCategory(historyFacts);
  const lastRun = runs[0];

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Card size="small" styles={{ body: { padding: 16 } }}>
        <Space style={{ width: '100%', justifyContent: 'space-between' }} wrap>
          <Space direction="vertical" size={0}>
            <Text strong>
              <BulbOutlined style={{ color: '#f59e0b' }} /> AI 客户洞察
            </Text>
            <Text type="secondary" style={{ fontSize: 12 }}>
              大模型自主规划调用 Jina 搜索 + LinkedIn 查询, 广撒网收集客户周边信息 (增量存档)
            </Text>
          </Space>
          {running ? (
            <Button icon={<StopOutlined />} danger onClick={stop}>中止</Button>
          ) : (
            <Button type="primary" icon={<PlayCircleOutlined />} onClick={start}>
              运行新洞察
            </Button>
          )}
        </Space>
        {(running || progress.done > 0) && (
          <Progress percent={pct} status={running ? 'active' : 'success'} style={{ marginTop: 12 }} />
        )}
        {lastRun && !running && (
          <Text type="secondary" style={{ fontSize: 12 }}>
            上次运行: {new Date(lastRun.started_at).toLocaleString()} · {lastRun.status} · 累计事实 {historyFacts.length} 条
          </Text>
        )}
      </Card>

      <Tabs
        items={[
          {
            key: 'live',
            label: <Space>本次执行 {liveFacts.length ? <Tag color="green">{liveFacts.length}</Tag> : null}</Space>,
            children: (
              <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                {summary && (
                  <Card size="small" title={<Space><ThunderboltOutlined /> 总结</Space>}>
                    <Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>{summary}</Paragraph>
                  </Card>
                )}
                {liveFacts.length > 0 && (
                  <Card size="small" title="本次新增事实">
                    <List
                      size="small"
                      dataSource={liveFacts}
                      renderItem={(f) => {
                        const meta = CATEGORY_META[f.category] || CATEGORY_META.other;
                        return (
                          <List.Item>
                            <Space align="start">
                              <Tag color={meta.color}>{meta.label}</Tag>
                              <Text>{f.content}</Text>
                              {f.source_url && (
                                <a href={f.source_url} target="_blank" rel="noreferrer">
                                  <LinkOutlined />
                                </a>
                              )}
                            </Space>
                          </List.Item>
                        );
                      }}
                    />
                  </Card>
                )}
                {stream.length === 0 ? (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="点击 “运行新洞察” 开始" />
                ) : (
                  <Card size="small" title={<Space><FileSearchOutlined /> 执行流</Space>} bodyStyle={{ maxHeight: 320, overflowY: 'auto' }}>
                    <Timeline
                      items={stream.map(({ ev, ts }) => ({
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
              </Space>
            ),
          },
          {
            key: 'archive',
            label: <Space>历史档案 <Tag color="blue">{historyFacts.length}</Tag></Space>,
            children: historyFacts.length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有历史洞察" />
            ) : (
              <Space direction="vertical" size="small" style={{ width: '100%' }}>
                {Object.entries(CATEGORY_META).map(([key, meta]) => {
                  const items = factsByCat[key] || [];
                  if (items.length === 0) return null;
                  return (
                    <Card key={key} size="small" title={<Space><Tag color={meta.color}>{meta.label}</Tag> <Text type="secondary">{items.length}</Text></Space>}>
                      <List
                        size="small"
                        dataSource={items}
                        renderItem={(f) => (
                          <List.Item>
                            <Space align="start">
                              <CloudOutlined style={{ color: '#9ca3af' }} />
                              <div>
                                <div>{f.content}</div>
                                <Text type="secondary" style={{ fontSize: 11 }}>
                                  {new Date(f.discovered_at).toLocaleString()}
                                  {f.source_url ? (
                                    <> · <a href={f.source_url} target="_blank" rel="noreferrer">来源</a></>
                                  ) : null}
                                </Text>
                              </div>
                            </Space>
                          </List.Item>
                        )}
                      />
                    </Card>
                  );
                })}
              </Space>
            ),
          },
          {
            key: 'runs',
            label: <Space>运行记录 <Tag>{runs.length}</Tag></Space>,
            children: runs.length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <List
                size="small"
                dataSource={runs}
                renderItem={(r) => (
                  <List.Item>
                    <Space direction="vertical" size={2} style={{ width: '100%' }}>
                      <Space>
                        <Tag color={r.status === 'completed' ? 'green' : r.status === 'failed' ? 'red' : 'blue'}>
                          {r.status}
                        </Tag>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {new Date(r.started_at).toLocaleString()}
                        </Text>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          步骤 {r.steps_done}/{r.steps_total}
                        </Text>
                      </Space>
                      {r.summary && (
                        <Paragraph ellipsis={{ rows: 2, expandable: true }} style={{ margin: 0, fontSize: 12 }}>
                          {r.summary}
                        </Paragraph>
                      )}
                      {r.error_message && <Text type="danger" style={{ fontSize: 12 }}>错误: {r.error_message}</Text>}
                    </Space>
                  </List.Item>
                )}
              />
            ),
          },
        ]}
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
  return {
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
  }[type] || type;
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
