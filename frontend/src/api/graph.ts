/** graph 模块 API 封装：关系字典/关系边/图数据，对应 backend graph/api.py */
import { api } from './client'
import type {
  GraphDataOut,
  KinshipOut,
  RelationshipCreate,
  RelationshipOut,
  RelationshipTypeCreate,
  RelationshipTypeOut,
} from './types'

export const graphApi = {
  /** 关系类型字典（按组与排序键稳定排序）。 */
  relationshipTypes: () =>
    api.get<RelationshipTypeOut[]>('/graph/relationship-types'),
  /** 新增自定义关系类型（重名 409）。 */
  createRelationshipType: (data: RelationshipTypeCreate) =>
    api.post<RelationshipTypeOut>('/graph/relationship-types', data),
  /** 图数据：center_id 缺省为全图；depth 1-5。 */
  graphData: (params?: { center_id?: number; depth?: number }) => {
    const query = new URLSearchParams()
    if (params?.center_id) query.set('center_id', String(params.center_id))
    if (params?.depth) query.set('depth', String(params.depth))
    const qs = query.toString()
    return api.get<GraphDataOut>(`/graph/data${qs ? `?${qs}` : ''}`)
  },
  /** 视角称谓推导（D15）：从"我"到目标的最短角色路径 + 中文称呼。 */
  kinship: (contactId: number) =>
    api.get<KinshipOut>(`/graph/kinship?contact_id=${contactId}`),
  /** 某联系人的关系列表（方向与标签按视角归一）。 */
  relationships: (contactId: number) =>
    api.get<RelationshipOut[]>(`/graph/relationships?contact_id=${contactId}`),
  /** 创建关系边（重复 409）。 */
  createRelationship: (data: RelationshipCreate) =>
    api.post<RelationshipOut>('/graph/relationships', data),
  /** 删除关系边（仅所有者）。 */
  removeRelationship: (edgeId: number) =>
    api.delete<void>(`/graph/relationships/${edgeId}`),
}
