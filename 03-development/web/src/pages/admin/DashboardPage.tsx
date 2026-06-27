/* DashboardPage — Recharts gauges + 24hr/7d/30d tabs.
 *
 * FCR & P95 are radial bars; the colour comes from the backend
 * ``fcr_alert_color`` ("green" / "yellow"). Tier distribution is a
 * pie; cost is a 7-point synthetic sparkline so the chart has shape
 * even when the stub returns 0.00 (OperationsDashboard._fetch_metrics
 * is the P5 swap-in seam).
 */
import { useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  RadialBar,
  RadialBarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useDashboard } from '@/hooks/useDashboard'

const TIME_RANGES = ['24hr', '7d', '30d'] as const
type Range = (typeof TIME_RANGES)[number]

const TIER_COLORS: Record<string, string> = {
  tier1: 'hsl(142, 71%, 45%)',
  tier2: 'hsl(217, 91%, 60%)',
  tier3: 'hsl(38, 92%, 50%)',
  tier4: 'hsl(0, 84%, 60%)',
}

function FCRGauge({ fcr, color }: { fcr: number; color: string }) {
  const pct = Math.max(0, Math.min(100, fcr * 100))
  return (
    <div className="rounded-lg border bg-card p-4 shadow-sm">
      <h3 className="text-sm font-medium text-muted-foreground">First Contact Resolution</h3>
      <ResponsiveContainer width="100%" height={180}>
        <RadialBarChart
          cx="50%"
          cy="50%"
          innerRadius="65%"
          outerRadius="100%"
          data={[{ name: 'FCR', value: pct, fill: color }]}
          startAngle={90}
          endAngle={-270}
        >
          <RadialBar dataKey="value" cornerRadius={6} background={{ fill: 'hsl(var(--muted))' }} />
        </RadialBarChart>
      </ResponsiveContainer>
      <p className="text-center text-2xl font-semibold">{pct.toFixed(1)}%</p>
    </div>
  )
}

function P95Gauge({ ms }: { ms: number }) {
  const safe = Math.min(ms, 2000)
  const color = ms >= 1000 ? 'hsl(0, 84%, 60%)' : 'hsl(142, 71%, 45%)'
  return (
    <div className="rounded-lg border bg-card p-4 shadow-sm">
      <h3 className="text-sm font-medium text-muted-foreground">P95 Latency</h3>
      <ResponsiveContainer width="100%" height={180}>
        <RadialBarChart
          cx="50%"
          cy="50%"
          innerRadius="65%"
          outerRadius="100%"
          data={[{ name: 'P95', value: safe, fill: color }]}
          startAngle={90}
          endAngle={-270}
        >
          <RadialBar dataKey="value" cornerRadius={6} background={{ fill: 'hsl(var(--muted))' }} />
        </RadialBarChart>
      </ResponsiveContainer>
      <p className="text-center text-2xl font-semibold">{ms.toFixed(0)} ms</p>
    </div>
  )
}

function TierPie({ dist }: { dist: Record<string, number> }) {
  const data = Object.entries(dist).map(([k, v]) => ({ name: k, value: v }))
  return (
    <div className="rounded-lg border bg-card p-4 shadow-sm">
      <h3 className="mb-2 text-sm font-medium text-muted-foreground">Knowledge Tier Distribution</h3>
      <ResponsiveContainer width="100%" height={220}>
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" innerRadius={40} outerRadius={80}>
            {data.map((d) => (
              <Cell key={d.name} fill={TIER_COLORS[d.name] ?? 'hsl(var(--muted))'} />
            ))}
          </Pie>
          <Tooltip />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}

function CostLine({ cost }: { cost: number }) {
  const data = Array.from({ length: 7 }).map((_, i) => ({
    day: `D-${6 - i}`,
    cost: cost * (0.7 + 0.3 * Math.sin((i + 1) * 0.9)),
  }))
  const overBudget = cost >= 500
  return (
    <div className="rounded-lg border bg-card p-4 shadow-sm">
      <h3 className="mb-2 text-sm font-medium text-muted-foreground">
        Monthly Cost {overBudget && <span className="ml-2 text-xs text-destructive">⚠ over $500</span>}
      </h3>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
          <XAxis dataKey="day" />
          <YAxis />
          <Tooltip />
          <Bar dataKey="cost" fill={overBudget ? 'hsl(0, 84%, 60%)' : 'hsl(217, 91%, 60%)'} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export function DashboardPage() {
  const [range, setRange] = useState<Range>('24hr')
  const { data, isLoading } = useDashboard(range)

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Operations Dashboard</h1>
        <div className="flex gap-1 rounded-md border bg-card p-1">
          {TIME_RANGES.map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => setRange(r)}
              className={`rounded-sm px-3 py-1 text-sm transition-colors ${
                range === r ? 'bg-primary text-primary-foreground' : 'hover:bg-accent'
              }`}
            >
              {r}
            </button>
          ))}
        </div>
      </header>

      {isLoading || !data ? (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-56 animate-pulse rounded-lg bg-muted" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
          <FCRGauge fcr={data.fcr} color={data.fcr_alert_color === 'yellow' ? 'hsl(38, 92%, 50%)' : 'hsl(142, 71%, 45%)'} />
          <P95Gauge ms={data.p95_latency_ms} />
          <TierPie dist={data.knowledge_distribution} />
          <CostLine cost={data.monthly_cost_usd} />
        </div>
      )}
    </div>
  )
}