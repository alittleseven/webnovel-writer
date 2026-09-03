import { useEffect, useState } from 'react'
import { useDashboardContext } from '../App.jsx'
import { fetchGovernance } from '../api.js'
import Badge from '../components/Badge.jsx'

// 治理面板（webnovel-copilot-300 M7/T32，F-14）：六组只读治理视图。
function Section({ title, children }) {
    return (
        <section className="card" style={{ marginBottom: 16 }}>
            <h3 style={{ margin: '0 0 8px' }}>{title}</h3>
            {children}
        </section>
    )
}

function Empty({ text }) {
    return <p style={{ color: '#888', margin: '4px 0' }}>{text}</p>
}

export default function GovernancePage() {
    const { refreshToken } = useDashboardContext()
    const [snapshot, setSnapshot] = useState(null)
    const [error, setError] = useState(null)

    useEffect(() => {
        fetchGovernance()
            .then(data => {
                setSnapshot(data)
                setError(null)
            })
            .catch(() => setError('治理快照加载失败（需要书项目上下文）'))
    }, [refreshToken])

    if (error) return <p>{error}</p>
    if (!snapshot) return <p>加载中…</p>

    const zones = snapshot.outline_zones?.zones || {}
    const freeze = snapshot.freeze || {}
    const journal = snapshot.journal || []
    const materials = snapshot.materials || {}
    const inflation = snapshot.inflation || {}
    const alerts = snapshot.alerts || {}

    return (
        <div>
            <h2>治理面板（只读）</h2>
            <Section title="① 总纲三区状态">
                {!snapshot.outline_zones?.has_master && <Empty text="总纲.md 未找到" />}
                {Object.keys(zones).length === 0 && snapshot.outline_zones?.has_master && <Empty text="未识别到甲/乙/丙区结构" />}
                <ul>
                    {Object.entries(zones).map(([zone, info]) => (
                        <li key={zone}>
                            {zone}：标题 {info['标题数']} 个，正文 {info['行数']} 行
                        </li>
                    ))}
                </ul>
            </Section>

            <Section title="② 冻结进度">
                {(freeze.versions || []).length === 0 && <Empty text="尚无定版快照" />}
                <ul>
                    {(freeze.versions || []).map(v => (
                        <li key={v.version}>
                            {v.version}（卷{v.volume}，{v.files} 文件，{v.frozen_at || '—'}）
                        </li>
                    ))}
                </ul>
                <p>演化事件：freeze/retcon 共 {freeze.events || 0} 次</p>
            </Section>

            <Section title="③ journal 时间线（最近 50 条，新→旧）">
                {journal.length === 0 && <Empty text="无事件（运行 author-sync 留账）" />}
                <ul>
                    {journal.slice(0, 20).map((event, index) => (
                        <li key={index}>
                            <Badge text={event.domain || '其他'} /> [{event.action}/{event.actor}] {event.summary || event.ts}
                        </li>
                    ))}
                </ul>
                {journal.length > 20 && <p style={{ color: '#888' }}>…共 {journal.length} 条</p>}
            </Section>

            <Section title="④ 素材热力">
                <ul>
                    {Object.entries(materials.tables || {}).map(([table, info]) => (
                        <li key={table}>
                            {table}：{info.total} 条（active {info.active}）
                        </li>
                    ))}
                </ul>
                {(materials.top_used || []).length > 0 && (
                    <>
                        <p>使用次数 Top：</p>
                        <ul>
                            {materials.top_used.map(item => (
                                <li key={item.id}>
                                    {item.id} × {item.uses}
                                </li>
                            ))}
                        </ul>
                    </>
                )}
            </Section>

            <Section title="⑤ 通胀曲线（力量锚点）">
                {(inflation.records || []).length === 0 && <Empty text="无通胀记录（settle 后自动追加）" />}
                <ul>
                    {(inflation.records || []).map(record => (
                        <li key={`${record.章}-${record.主角锚点}`}>
                            第{record.章}章 {record.主角锚点} {record.事件}
                            {record.偏差 ? `（${record.偏差}）` : ''}
                        </li>
                    ))}
                </ul>
                <p>战例账本：{inflation.battles || 0} 条</p>
            </Section>

            <Section title="⑥ 红点（stale / 逾期 / 画廊积压）">
                <p>
                    stale 未消费：{alerts.stale?.length || 0}｜伏笔逾期：{alerts.overdue?.length || 0}｜画廊文件：{alerts.gallery_files || 0}
                </p>
                {(alerts.overdue || []).map(item => (
                    <p key={item.编号} style={{ color: '#e5534b' }}>
                        逾期 {item.编号}「{item.名称}」最晚回收章 {item.最晚回收章}
                    </p>
                ))}
                {(alerts.stale || []).map((item, index) => (
                    <p key={index} style={{ color: '#d29922' }}>
                        stale {item.target}：{item.reason}
                    </p>
                ))}
            </Section>
        </div>
    )
}
