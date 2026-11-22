import { useState } from 'react'
import { Popover } from 'antd'
import { useControls } from '../../useControls.js'
import { DownOutlined, LeftOutlined, RightOutlined, FilterOutlined, ReloadOutlined, SearchOutlined, SyncOutlined, UpOutlined } from '@ant-design/icons'
import { SORT_OPTIONS, ORDER_OPTIONS, PAGE_SIZE_OPTIONS, RECOMMEND_PERCENT_OPTIONS } from '../../shared.jsx'
import { DEFAULT_FILTERS, HOT_DAY_VALUES, MAX_HOT_PERIOD, hotPeriodRange } from './filters.js'
import MobileSheet from '../../MobileSheet.jsx'

const VIEW_MODE_OPTIONS = [{ label: '随机推荐', value: 'recommend' }, { label: '近期热帖', value: 'hot' }, { label: '全部帖子', value: 'all' }]
const HOT_DAY_OPTIONS = HOT_DAY_VALUES.map(value => ({ label: `${value} 天`, value }))

export default function ThreadFilters({ searchOpen, onToggleSeen, form, filters, isMobile, forumOptions, loading, showActions, setShowActions, mobileFiltersOpen, setMobileFiltersOpen, advancedFiltersOpen, setAdvancedFiltersOpen, handleSearch, handleViewModeChange, handleHotDaysChange, handleHotPeriodChange, handleShuffle, handleReset }) {
  const { Button, DatePicker, Form, Input, InputNumber, Segmented, Select, Switch } = useControls()
  const { RangePicker } = DatePicker
  function renderFilterActions() {
    return <div className="advanced-filter-actions">
              <Button type="primary" htmlType={isMobile ? "button" : "submit"} onClick={isMobile ? () => form.submit() : undefined} loading={loading}>应用筛选</Button>
              <Button className="mobile-quiet-action" icon={<ReloadOutlined />} onClick={handleReset}>重置筛选</Button>
              <Button type="text" icon={<UpOutlined />} onClick={() => {
                setMobileFiltersOpen(false)
                setAdvancedFiltersOpen(false)
              }}>收起</Button>
            </div>
  }
  const FilterSurface = isMobile ? MobileSheet : 'div'
  const filterSurfaceProps = isMobile ? { title: '筛选帖子', open: mobileFiltersOpen, forceRender: true, onClose: () => setMobileFiltersOpen(false), className: 'thread-filter-drawer', footer: renderFilterActions() } : {}
  const [customDaysOpen, setCustomDaysOpen] = useState(false)
  const [customDays, setCustomDays] = useState(14)
  const periodRange = hotPeriodRange(filters)
  const period = filters.hot_period || 0
  const sameYear = periodRange.from.slice(0, 4) === periodRange.to.slice(0, 4)
  const periodLabel = sameYear ? `${periodRange.from.slice(0, 4) === String(new Date().getFullYear()) ? '' : periodRange.from.slice(0, 4) + '/'}${periodRange.from.slice(5).replace('-', '/')}–${periodRange.to.slice(5).replace('-', '/')}` : `${periodRange.from}–${periodRange.to}`
  const validCustomDays = Number.isInteger(customDays) && customDays >= 1 && customDays <= 365
  function applyCustomDays() {
    if (!validCustomDays) return
    handleHotDaysChange(customDays)
    setCustomDaysOpen(false)
  }
  function openCustomDays(open) {
    setCustomDaysOpen(open)
    if (open) setCustomDays(filters.hot_days)
  }
  const customDaysTrigger = <Button className="hot-days-custom-trigger" type="text" onClick={isMobile ? () => openCustomDays(true) : undefined}>{period === 0 && !filters.hot_anchor ? '近' : '每期'} {filters.hot_days} 天 <DownOutlined /></Button>
  const periodControls = (
    <div className="hot-period-controls">
      <Button type="text" icon={<LeftOutlined />} aria-label="上一周期" disabled={period >= MAX_HOT_PERIOD} onClick={() => handleHotPeriodChange(period + 1)} />
      <span className="hot-period-range" aria-live="polite" aria-label={`${periodRange.from} 至 ${periodRange.to}`} title={`${periodRange.from} 至 ${periodRange.to}`}>{periodLabel}</span>
      <Button type="text" icon={<RightOutlined />} aria-label="下一周期" disabled={period === 0} onClick={() => handleHotPeriodChange(period - 1)} />
      {(period > 0 || filters.hot_anchor) && <Button type="link" className="hot-period-reset" aria-label="回到最近" onClick={() => handleHotPeriodChange(0, true)}>最近</Button>}
    </div>
  )
  const customDaysContent = <div className="hot-days-custom-panel">
    {isMobile && periodControls}
    <Segmented block aria-label="常用周期天数" options={HOT_DAY_OPTIONS} value={customDays} onChange={setCustomDays} />
    <label htmlFor="custom-hot-days">自定义天数（1–365）</label>
    <InputNumber id="custom-hot-days" inputMode="numeric" size={isMobile ? 'large' : 'middle'} min={1} max={365} precision={0} value={customDays} onChange={setCustomDays} onPressEnter={(event) => { event.preventDefault(); event.stopPropagation(); applyCustomDays() }} style={{ width: '100%' }} />
    <div className="hot-days-custom-actions">
      {isMobile && <Button size="large" onClick={() => setCustomDaysOpen(false)}>取消</Button>}
      <Button size={isMobile ? 'large' : 'middle'} type="primary" disabled={!validCustomDays} onClick={applyCustomDays} block>应用</Button>
    </div>
  </div>
  const periodNavigation = filters.view_mode === 'hot' && <div className="hot-period-navigation" aria-label="热帖周期切换">
    {isMobile ? customDaysTrigger : <Popover trigger="click" open={customDaysOpen} onOpenChange={openCustomDays} title="时间范围" content={customDaysContent}>{customDaysTrigger}</Popover>}
    {periodControls}
  </div>
  return (
<section className={'query-panel thread-query-panel' + (isMobile ? ' compact-reader-query' : '')}>
        <Form form={form} layout="inline" initialValues={DEFAULT_FILTERS} onFinish={handleSearch}>
          {isMobile ? <>
            <div className="compact-reader-modes" role="group" aria-label="浏览模式">
              {[VIEW_MODE_OPTIONS[1], VIEW_MODE_OPTIONS[0], VIEW_MODE_OPTIONS[2]].map(({ value, label }) => (
                <Button type="text" key={value} aria-pressed={filters.view_mode === value}
                  onClick={() => handleViewModeChange(value)}>{label}</Button>
              ))}
            </div>
            <div className="compact-reader-tools">
              {filters.view_mode === 'hot' && <Button type="text" onClick={() => openCustomDays(true)}>
                <span>{period === 0 && !filters.hot_anchor ? '近' : '每期'} {filters.hot_days} 天 <DownOutlined /></span>
              </Button>}
              <Button type="text" aria-pressed={filters.hide_seen} onClick={onToggleSeen}>
                <span>{filters.hide_seen ? '✓ 隐藏已看' : '隐藏已看'}</span>
              </Button>
              <Button type="text" aria-expanded={mobileFiltersOpen} onClick={() => setMobileFiltersOpen(true)}><span>筛选</span></Button>
              {filters.view_mode === 'recommend' && <Button type="text" disabled={loading} onClick={handleShuffle}><span>换一批</span></Button>}
            </div>
          </> : <div className="browse-mode-row">
            <div className="browse-mode-control">
              <span className="browse-mode-label">浏览模式</span>
              <Segmented aria-label="浏览模式" options={VIEW_MODE_OPTIONS}
                value={filters.view_mode} onChange={handleViewModeChange} />
            </div>
            {periodNavigation}
          </div>}
          {(!isMobile || searchOpen) && <div className="primary-filter-row">
            <Form.Item name="q" className="primary-search-item">
              <Input
                allowClear
                aria-label="搜索帖子标题或 TID"
                prefix={<SearchOutlined />}
                placeholder="搜索标题关键词或 TID"
                className="primary-search-input"
              />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} icon={<SearchOutlined />} className="search-submit">查询</Button>
            {!isMobile && <Form.Item name="fid" className="primary-forum-item">
              <Select aria-label="板块" options={forumOptions} placeholder="全部板块" className="forum-select" onChange={() => form.submit()} />
            </Form.Item>}
            {filters.view_mode === 'all' && !isMobile && (
              <Form.Item name="sort" className="primary-sort-item">
                <Select aria-label="帖子排序" options={SORT_OPTIONS} className="sort-select" onChange={() => form.submit()} />
              </Form.Item>
            )}
            {!isMobile && <div className="primary-filter-actions">
            {filters.view_mode === 'recommend' && <Button type="text" className="recommend-shuffle" icon={<SyncOutlined />} loading={loading} onClick={handleShuffle}>换一批</Button>}
            <Button
              type="text"
              icon={<FilterOutlined />}
              className="advanced-filter-trigger"
              aria-expanded={isMobile ? mobileFiltersOpen : advancedFiltersOpen}
              aria-controls="thread-advanced-filters"
              onClick={() => {
                if (isMobile) setMobileFiltersOpen((open) => !open)
                else setAdvancedFiltersOpen((open) => !open)
              }}
            >
              筛选
            </Button>
            </div>}
          </div>}

          <FilterSurface {...filterSurfaceProps}>
          <div id="thread-advanced-filters" className={`advanced-filter-panel ${(isMobile ? mobileFiltersOpen : advancedFiltersOpen) ? 'is-open' : ''}`}>
            {isMobile && <Form.Item name="fid" label="板块"><Select options={forumOptions} /></Form.Item>}
            {filters.view_mode === 'all' && isMobile && (
              <Form.Item name="sort" label="排序"><Select options={SORT_OPTIONS} /></Form.Item>
            )}
            <Form.Item name="exclude_q" label="排除关键词">
              <Input allowClear placeholder="空格、逗号分隔多个词" className="keyword-input" />
            </Form.Item>
            {filters.view_mode === 'hot' ? (
              <div className="hot-mode-hint">近期热帖按回复数降序展示，无需设置日期与排序。</div>
            ) : filters.view_mode === 'all' && isMobile ? (
              <Form.Item label="日期" className="date-filter-item">
                <div className="mobile-date-range">
                  <Form.Item name={['dateRange', 0]} noStyle><DatePicker inputReadOnly allowClear placeholder="开始日期" /></Form.Item>
                  <Form.Item name={['dateRange', 1]} noStyle><DatePicker inputReadOnly allowClear placeholder="结束日期" /></Form.Item>
                </div>
              </Form.Item>
            ) : filters.view_mode === 'all' ? (
              <Form.Item name="dateRange" label="日期" className="date-filter-item"><RangePicker allowClear /></Form.Item>
            ) : null}
            {filters.view_mode === 'all' && (
              <Form.Item name="order" label="顺序"><Select options={ORDER_OPTIONS} className="order-select" /></Form.Item>
            )}
            {filters.view_mode !== 'recommend' && (
              <Form.Item name="page_size" label="每页"><Select options={PAGE_SIZE_OPTIONS} className="page-size-select" /></Form.Item>
            )}
            {filters.view_mode === 'recommend' && (
              <Form.Item name="recommend_top_percent" label="推荐范围" className="recommend-percent-filter-item">
                <Select options={RECOMMEND_PERCENT_OPTIONS} className="recommend-percent-select" />
              </Form.Item>
            )}
            <Form.Item name="show_disliked" label="显示不感兴趣" valuePropName="checked"><Switch /></Form.Item>
            {!isMobile && filters.view_mode !== 'hot' && (
              <Form.Item name="hide_seen" label="隐藏已看" valuePropName="checked"><Switch /></Form.Item>
            )}
            <Form.Item name="only_liked" label="只看感兴趣" valuePropName="checked"><Switch /></Form.Item>
            <Form.Item label="显示操作"><Switch checked={showActions} onChange={setShowActions} /></Form.Item>
            {!isMobile && renderFilterActions()}
          </div>
          </FilterSurface>
        </Form>
        {isMobile && <MobileSheet title="时间范围" className="hot-days-custom-drawer" open={customDaysOpen && filters.view_mode === 'hot'} onClose={() => setCustomDaysOpen(false)}>{customDaysContent}</MobileSheet>}
      </section>
  )
}
