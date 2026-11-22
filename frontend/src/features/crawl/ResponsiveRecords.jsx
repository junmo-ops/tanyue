import { useState } from 'react'
import { Empty, Grid, Pagination, Table } from 'antd'

// Keep the same fields and actions in desktop tables and mobile cards.
export default function ResponsiveRecords({ columns, dataSource, pagination, renderMobileActions, ...props }) {
  const screens = Grid.useBreakpoint()
  const [page, setPage] = useState(1)
  if (screens.md !== false) return <Table {...props} columns={columns} dataSource={dataSource} pagination={pagination} />

  const pageSize = pagination?.pageSize || 10
  const current = Math.min(page, Math.max(1, Math.ceil(dataSource.length / pageSize)))
  const rows = pagination === false ? dataSource : dataSource.slice((current - 1) * pageSize, current * pageSize)
  const mobileColumns = renderMobileActions ? columns.filter((column) => column.key !== 'actions') : columns
  return <div className="crawl-mobile-records">
    {!rows.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无记录" />}
    {rows.map((row, index) => <article className="crawl-record" key={row[props.rowKey]}>
      {mobileColumns.map((column, columnIndex) => {
        const value = row[column.dataIndex]
        const content = column.render ? column.render(value, row, index) : value
        return columnIndex === 0
          ? <h4 key={columnIndex}>{content}</h4>
          : <div className="crawl-record-field" key={columnIndex}><span className="crawl-record-label">{column.title}</span><div>{content}</div></div>
      })}
      {renderMobileActions && <div className="crawl-record-actions">{renderMobileActions(row)}</div>}
    </article>)}
    {pagination !== false && dataSource.length > pageSize && <Pagination simple current={current} pageSize={pageSize} total={dataSource.length} onChange={setPage} showSizeChanger={false} />}
  </div>
}
