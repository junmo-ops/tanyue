import { createContext, useContext } from 'react'
import { Alert, Button, Card, Checkbox, Collapse, DatePicker, Descriptions, Drawer, Dropdown, Empty, Form, Input, InputNumber, List, Modal, Pagination, Progress, Segmented, Select, Skeleton, Space, Spin, Switch, Tabs, Tag, Typography, message } from 'antd'

const desktopControls = { Alert, Button, Card, Checkbox, Collapse, DatePicker, Descriptions, Drawer, Dropdown, Empty, Form, Input, InputNumber, List, Modal, Pagination, Progress, Segmented, Select, Skeleton, Space, Spin, Switch, Tabs, Tag, Typography, message }
export const ControlsContext = createContext(desktopControls)
export function useControls() { return useContext(ControlsContext) }
