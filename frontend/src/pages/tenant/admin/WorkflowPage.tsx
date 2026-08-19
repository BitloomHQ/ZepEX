import { GitBranch, Plus, Trash2, UserCog } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { isAxiosError } from 'axios'
import {
  addWorkflowStep,
  deactivateWorkflowStep,
  deleteApprovalWorkflow,
  getApprovalWorkflow,
  listApprovalWorkflows,
  listCompanyRoles,
  listDepartments,
  listEmployees,
  saveApprovalWorkflow,
  updateCompanyWorkflow,
  updateWorkflowStep,
} from '@/api'
import { getApiErrorMessage } from '@/api/client'
import { AdminListPanel } from '@/components/admin/AdminListPanel'
import { AdminConfirmDialog } from '@/components/admin/AdminConfirmDialog'
import { WorkflowBuilder } from '@/components/workflow/WorkflowBuilder'
import { WorkflowSimulationPanel } from '@/components/workflow/WorkflowSimulationPanel'
import type { ApprovalNodeData } from '@/components/workflow/types'
import type { WorkflowNode } from '@/components/workflow/types'
import { DashboardLayout } from '@/components/layout/DashboardLayout'
import { invalidateAdminSetupCache, useAdminNav } from '@/hooks/useAdminNav'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { WorkflowPageShimmer } from '@/components/ui/shimmer'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { fetchAllPages } from '@/lib/pagination'
import { cn } from '@/lib/utils'
import { toast } from '@/lib/toast'
import type { ApprovalWorkflow, ApprovalWorkflowStep, CompanyRole, DepartmentRecord, EmployeeRecord } from '@/types'

const selectClassName =
  'flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm'

function getActiveSteps(workflow: ApprovalWorkflow | null): ApprovalWorkflowStep[] {
  return (workflow?.steps ?? [])
    .filter((step) => step.is_active)
    .sort((a, b) => a.step_order - b.step_order)
}

function resolveCanvasStepIds(
  orderedNodes: WorkflowNode[],
  activeSteps: ApprovalWorkflowStep[],
): Array<string | undefined> {
  const usedStepIds = new Set<string>()

  return orderedNodes.map((node) => {
    const data = node.data as ApprovalNodeData

    if (data.backendStepId) {
      usedStepIds.add(data.backendStepId)
      return data.backendStepId
    }

    const match = activeSteps.find(
      (step) =>
        !usedStepIds.has(step.id) &&
        step.approver_role === data.roleId &&
        step.routing_type === data.routingType &&
        (step.department || null) === (data.departmentId || null),
    )

    if (match) {
      usedStepIds.add(match.id)
      return match.id
    }

    return undefined
  })
}

async function loadWorkflowList(): Promise<ApprovalWorkflow[]> {
  try {
    const { data } = await listApprovalWorkflows()
    return data.workflows ?? []
  } catch (err) {
    if (isAxiosError(err) && err.response?.status === 404) {
      return []
    }
    throw err
  }
}

export function WorkflowPage() {
  const { navItems } = useAdminNav()
  const [workflows, setWorkflows] = useState<ApprovalWorkflow[]>([])
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string | null>(null)
  const [roles, setRoles] = useState<CompanyRole[]>([])
  const [departments, setDepartments] = useState<DepartmentRecord[]>([])
  const [employees, setEmployees] = useState<EmployeeRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false)
  const [workflowName, setWorkflowName] = useState('Default Approval Workflow')
  const [selectedName, setSelectedName] = useState('')
  const [startRoleId, setStartRoleId] = useState<number | ''>('')

  const selectedWorkflow = useMemo(
    () => workflows.find((item) => item.id === selectedWorkflowId) ?? null,
    [workflows, selectedWorkflowId],
  )

  useEffect(() => {
    setSelectedName(selectedWorkflow?.name ?? '')
  }, [selectedWorkflow])

  const activeSteps = getActiveSteps(selectedWorkflow)

  const submitterRoles = useMemo(
    () => roles.filter((role) => role.can_submit_expense),
    [roles],
  )

  const approverRoles = useMemo(
    () => roles.filter((role) => role.can_approve_expense || role.can_mark_paid),
    [roles],
  )

  const availableStartRoles = useMemo(
    () =>
      submitterRoles.filter(
        (role) => !workflows.some((workflow) => workflow.start_role === role.id),
      ),
    [submitterRoles, workflows],
  )

  const openCreateWorkflowModal = useCallback(() => {
    const nextRole = availableStartRoles[0]
    if (nextRole) {
      setStartRoleId(nextRole.id)
      setWorkflowName(`${nextRole.name} Approval Workflow`)
    }
    setCreateOpen(true)
  }, [availableStartRoles])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [rolesRes, allDepartments, allEmployees, workflowList] = await Promise.all([
        listCompanyRoles(),
        fetchAllPages((page) => listDepartments({ page })),
        fetchAllPages((page) => listEmployees({ page })),
        loadWorkflowList(),
      ])

      const activeRoles = rolesRes.data.results.filter((role) => role.is_active)
      setRoles(activeRoles)
      setDepartments(allDepartments.filter((department) => department.is_active !== false))
      setEmployees(allEmployees)
      setWorkflows(workflowList)

      setSelectedWorkflowId((current) => {
        if (current && workflowList.some((workflow) => workflow.id === current)) {
          return current
        }
        return workflowList[0]?.id ?? null
      })

      const firstAvailable = activeRoles.find(
        (role) =>
          role.can_submit_expense &&
          !workflowList.some((workflow) => workflow.start_role === role.id),
      )
      if (firstAvailable) {
        setStartRoleId((current) => current || firstAvailable.id)
        setWorkflowName((current) =>
          current === 'Default Approval Workflow'
            ? `${firstAvailable.name} Approval Workflow`
            : current,
        )
      }
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const refreshWorkflows = useCallback(
    async (preferredWorkflowId?: string | null) => {
      const workflowList = await loadWorkflowList()
      setWorkflows(workflowList)

      const nextId =
        preferredWorkflowId &&
        workflowList.some((workflow) => workflow.id === preferredWorkflowId)
          ? preferredWorkflowId
          : workflowList.find((workflow) => workflow.id === selectedWorkflowId)?.id ??
            workflowList[0]?.id ??
            null

      setSelectedWorkflowId(nextId)

      if (nextId) {
        const { data } = await getApprovalWorkflow(nextId)
        setWorkflows((prev) =>
          prev.map((workflow) => (workflow.id === nextId ? data : workflow)),
        )
        return data
      }

      return null
    },
    [selectedWorkflowId],
  )

  const handleCreateWorkflow = async () => {
    if (!startRoleId) {
      toast.error('Select which role this workflow applies to.')
      return
    }

    setSaving(true)
    setError('')
    try {
      const { data } = await saveApprovalWorkflow({
        name: workflowName.trim() || 'Approval Workflow',
        start_role: startRoleId,
      })

      await refreshWorkflows(data.workflow.id)
      setCreateOpen(false)
      toast.success(`Workflow created for ${data.workflow.start_role_name ?? 'role'}.`)
      invalidateAdminSetupCache()
    } catch (err) {
      toast.error(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const handleCreateDefault = async () => {
    if (!startRoleId) {
      toast.error('Select which role this workflow applies to.')
      return
    }

    setSaving(true)
    setError('')
    try {
      const managerRole = roles.find((role) => role.can_approve_expense)
      const accountsRole = roles.find((role) => role.can_mark_paid)

      if (!managerRole) {
        toast.error('Create a company role with approve expense permission first.')
        return
      }

      const { data } = await saveApprovalWorkflow({
        name: workflowName.trim() || 'Default Approval Workflow',
        start_role: startRoleId,
      })

      const workflowId = data.workflow.id

      await addWorkflowStep({
        workflow_id: workflowId,
        step_order: 1,
        approver_role: managerRole.id,
        approver_type: 'COMPANY_ROLE',
        routing_type: 'COMPANY',
      })

      if (accountsRole) {
        await addWorkflowStep({
          workflow_id: workflowId,
          step_order: 2,
          approver_role: accountsRole.id,
          approver_type: 'COMPANY_ROLE',
          routing_type: 'COMPANY',
        })
      }

      await refreshWorkflows(workflowId)
      setCreateOpen(false)
      toast.success(
        accountsRole
          ? 'Default workflow created: Manager → Accounts.'
          : 'Workflow created with manager approval step.',
      )
      invalidateAdminSetupCache()
    } catch (err) {
      toast.error(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const handleRenameWorkflow = async () => {
    if (!selectedWorkflow) return
    const name = selectedName.trim()
    if (!name) {
      toast.error('Workflow name is required.')
      return
    }
    if (name === selectedWorkflow.name) return

    setSaving(true)
    setError('')
    try {
      await updateCompanyWorkflow(selectedWorkflow.id, { name })
      await refreshWorkflows(selectedWorkflow.id)
      toast.success('Workflow name updated.')
    } catch (err) {
      toast.error(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteStep = async (stepId: string) => {
    if (!selectedWorkflow) return

    setSaving(true)
    setError('')
    try {
      await deactivateWorkflowStep(stepId)
      await refreshWorkflows(selectedWorkflow.id)
      toast.success('Step removed from workflow.')
      invalidateAdminSetupCache()
    } catch (err) {
      toast.error(getApiErrorMessage(err))
      throw err
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteWorkflow = async () => {
    if (!selectedWorkflow) return

    setSaving(true)
    setError('')
    try {
      const { data } = await deleteApprovalWorkflow(selectedWorkflow.id)
      setDeleteConfirmOpen(false)
      await refreshWorkflows()
      toast.success(data.message || 'Workflow deleted.')
      invalidateAdminSetupCache()
    } catch (err) {
      toast.error(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const handleSaveStepsFromCanvas = async (approvalNodes: WorkflowNode[]) => {
    if (!selectedWorkflow) return

    setSaving(true)
    setError('')
    try {
      for (const node of approvalNodes) {
        const data = node.data as ApprovalNodeData
        if (!data.roleId) {
          toast.error(`Approval node "${data.label}" needs a company role before saving.`)
          return
        }
      }

      const canvasStepIds = new Set(
        approvalNodes
          .map((node) => (node.data as ApprovalNodeData).backendStepId)
          .filter((id): id is string => Boolean(id)),
      )

      for (const step of activeSteps) {
        if (!canvasStepIds.has(step.id)) {
          await deactivateWorkflowStep(step.id)
        }
      }

      let workflowData = await refreshWorkflows(selectedWorkflow.id)
      let currentActive = getActiveSteps(workflowData)

      const newNodes = approvalNodes.filter(
        (node) => !(node.data as ApprovalNodeData).backendStepId,
      )

      if (newNodes.length > 0) {
        let nextOrder =
          currentActive.length > 0
            ? Math.max(...currentActive.map((step) => step.step_order)) + 1
            : 1

        for (const node of newNodes) {
          const data = node.data as ApprovalNodeData
          await addWorkflowStep({
            workflow_id: selectedWorkflow.id,
            step_order: nextOrder,
            approver_role: data.roleId!,
            approver_type: 'COMPANY_ROLE',
            routing_type: data.routingType,
            department: data.routingType === 'DEPARTMENT' ? data.departmentId || null : null,
          })
          nextOrder += 1
        }

        workflowData = await refreshWorkflows(selectedWorkflow.id)
        currentActive = getActiveSteps(workflowData)
      }

      let stepIds = resolveCanvasStepIds(approvalNodes, currentActive)

      for (let index = 0; index < approvalNodes.length; index += 1) {
        const stepId = stepIds[index]
        if (!stepId) continue

        const data = approvalNodes[index].data as ApprovalNodeData
        const step = currentActive.find((item) => item.id === stepId)
        if (!step) continue

        const targetOrder = index + 1
        const targetDepartment =
          data.routingType === 'DEPARTMENT' ? data.departmentId || null : null
        const orderChanged = step.step_order !== targetOrder
        const fieldsChanged =
          step.approver_role !== data.roleId ||
          step.routing_type !== data.routingType ||
          (step.department || null) !== (targetDepartment || null)

        if (!orderChanged && !fieldsChanged) continue

        await updateWorkflowStep(stepId, {
          step_order: targetOrder,
          approver_role: data.roleId!,
          routing_type: data.routingType,
          department: targetDepartment,
        })

        if (orderChanged) {
          workflowData = await refreshWorkflows(selectedWorkflow.id)
          currentActive = getActiveSteps(workflowData)
          stepIds = resolveCanvasStepIds(approvalNodes, currentActive)
        }
      }

      await refreshWorkflows(selectedWorkflow.id)
      toast.success('Workflow saved.')
      invalidateAdminSetupCache()
    } catch (err) {
      toast.error(getApiErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <DashboardLayout
        title="Approval Workflow"
        subtitle="Define approval paths per submitter role"
        breadcrumb="Approval Workflow"
        icon={GitBranch}
        navItems={navItems}
      >
        <WorkflowPageShimmer />
      </DashboardLayout>
    )
  }

  const needsRolesFirst = approverRoles.length === 0
  const needsSubmitterRoles = submitterRoles.length === 0

  return (
    <DashboardLayout
      title="Approval Workflow"
      subtitle="Each workflow applies when an employee with the selected start role submits expenses"
      breadcrumb="Approval Workflow"
      icon={GitBranch}
      navItems={navItems}
    >
      {error && (
        <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      {needsRolesFirst ? (
        <AdminListPanel
          title="Roles required"
          description="Workflow steps need at least one company role that can approve expenses or mark reports as paid."
        >
          <div className="flex flex-col items-center px-5 py-12 text-center sm:px-6">
            <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-amber-50">
              <UserCog className="h-7 w-7 text-amber-600" />
            </div>
            <h3 className="text-lg font-semibold text-gray-900">
              Please create a role first to create a workflow
            </h3>
            <p className="mt-2 max-w-md text-sm text-gray-500">
              Go to Roles and add permission profiles with approve or payment access, then return
              here to build your approval flow.
            </p>
            <div className="mt-6 flex flex-wrap justify-center gap-2">
              <Button asChild>
                <Link to="/admin/roles">Go to Roles</Link>
              </Button>
            </div>
          </div>
        </AdminListPanel>
      ) : needsSubmitterRoles ? (
        <AdminListPanel
          title="Submitter roles required"
          description="Workflows are assigned to roles that can submit expense reports."
        >
          <div className="flex flex-col items-center px-5 py-12 text-center sm:px-6">
            <p className="max-w-md text-sm text-gray-500">
              Enable <strong>Submit expense</strong> on at least one company role (for example
              Employee), then return here to create workflows.
            </p>
            <Button asChild className="mt-6">
              <Link to="/admin/roles">Go to Roles</Link>
            </Button>
          </div>
        </AdminListPanel>
      ) : (
        <div className="space-y-4">
          <div className="rounded-lg border border-[#e2e8f0] bg-white">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#e2e8f0] px-4 py-3 sm:px-5">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Workflows
              </p>
              <div className="flex flex-wrap items-center gap-2">
                {selectedWorkflow && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={saving}
                    className="text-red-600 hover:bg-red-50 hover:text-red-700"
                    onClick={() => setDeleteConfirmOpen(true)}
                  >
                    <Trash2 className="h-4 w-4" />
                    Delete
                  </Button>
                )}
                <Button
                  type="button"
                  size="sm"
                  disabled={saving || availableStartRoles.length === 0}
                  onClick={openCreateWorkflowModal}
                >
                  <Plus className="h-4 w-4" />
                  New workflow
                </Button>
              </div>
            </div>

            <p className="border-b border-[#e2e8f0] px-4 py-2 text-xs text-muted-foreground sm:px-5">
              One workflow per role that can <span className="font-medium text-gray-700">submit expenses</span>.
              Approver-only roles (e.g. CEO, Accounts) are not listed here.
              {availableStartRoles.length === 0 && submitterRoles.length > 0
                ? ' You already have a workflow for each submitter role.'
                : ''}
            </p>

            {workflows.length > 0 && (
              <div className="flex flex-wrap gap-2 px-4 py-3 sm:px-5">
                {workflows.map((workflow) => {
                  const selected = workflow.id === selectedWorkflowId
                  return (
                    <button
                      key={workflow.id}
                      type="button"
                      onClick={() => setSelectedWorkflowId(workflow.id)}
                      className={cn(
                        'rounded-full border px-4 py-2 text-sm font-medium transition-colors',
                        selected
                          ? 'border-primary bg-primary text-white'
                          : 'border-gray-200 bg-white text-gray-700 hover:border-primary/40 hover:bg-blue-50',
                      )}
                    >
                      {workflow.start_role_name || workflow.name}
                      <span
                        className={cn(
                          'ml-2 text-xs',
                          selected ? 'text-blue-100' : 'text-gray-400',
                        )}
                      >
                        {getActiveSteps(workflow).length} step
                        {getActiveSteps(workflow).length === 1 ? '' : 's'}
                      </span>
                    </button>
                  )
                })}
              </div>
            )}

            {selectedWorkflow && (
              <div className="space-y-3 border-t border-[#e2e8f0] px-4 py-3 text-sm sm:px-5">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
                  <div className="min-w-0 flex-1 space-y-1.5">
                    <Label htmlFor="selected-workflow-name">Workflow name</Label>
                    <Input
                      id="selected-workflow-name"
                      value={selectedName}
                      onChange={(e) => setSelectedName(e.target.value)}
                      disabled={saving}
                    />
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    disabled={saving || !selectedName.trim() || selectedName.trim() === selectedWorkflow.name}
                    onClick={() => void handleRenameWorkflow()}
                  >
                    Save name
                  </Button>
                </div>
                <p className="text-muted-foreground">
                  Submitter role:{' '}
                  <span className="font-medium text-gray-800">
                    {selectedWorkflow.start_role_name}
                  </span>
                </p>
              </div>
            )}
          </div>

          {!selectedWorkflow ? (
            <AdminListPanel
              title="No workflows yet"
              description="Create a workflow for each submitter role that needs its own approval path."
            >
              <div className="px-5 py-8 text-center sm:px-6">
                <p className="text-sm text-gray-500">
                  For example: Employee → Manager → Finance → Accounts, or a shorter path for
                  managers.
                </p>
                <Button
                  className="mt-4"
                  onClick={openCreateWorkflowModal}
                  disabled={availableStartRoles.length === 0}
                >
                  <Plus className="h-4 w-4" />
                  Create first workflow
                </Button>
              </div>
            </AdminListPanel>
          ) : selectedWorkflow ? (
            <WorkflowBuilder
              key={selectedWorkflow.id}
              steps={activeSteps}
              roles={roles}
              departments={departments}
              saving={saving}
              onSaveSteps={handleSaveStepsFromCanvas}
              onDeleteStep={handleDeleteStep}
            />
          ) : null}

          <WorkflowSimulationPanel employees={employees} disabled={saving} />

          <Dialog open={createOpen} onOpenChange={setCreateOpen}>
            <DialogContent className="max-w-lg">
              <DialogHeader>
                <DialogTitle>Create workflow</DialogTitle>
                <DialogDescription>
                  Choose which submitter role uses this approval path.
                </DialogDescription>
              </DialogHeader>
              <div className="grid min-w-0 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="start-role">Start role</Label>
                  <select
                    id="start-role"
                    className={selectClassName}
                    value={startRoleId}
                    onChange={(e) => {
                      const roleId = Number(e.target.value)
                      setStartRoleId(roleId)
                      const role = roles.find((item) => item.id === roleId)
                      if (role) {
                        setWorkflowName(`${role.name} Approval Workflow`)
                      }
                    }}
                  >
                    <option value="" disabled>
                      Select role
                    </option>
                    {availableStartRoles.map((role) => (
                      <option key={role.id} value={role.id}>
                        {role.name}
                      </option>
                    ))}
                  </select>
                  <p className="text-xs text-muted-foreground">
                    Employees with this role will follow this workflow when they submit reports.
                  </p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="workflow-name">Workflow name</Label>
                  <Input
                    id="workflow-name"
                    value={workflowName}
                    onChange={(e) => setWorkflowName(e.target.value)}
                  />
                </div>
              </div>
              <DialogFooter className="flex-col gap-2 sm:flex-col">
                <Button
                  type="button"
                  variant="outline"
                  className="w-full"
                  disabled={
                    saving ||
                    !startRoleId ||
                    !roles.some((role) => role.can_approve_expense)
                  }
                  onClick={handleCreateDefault}
                >
                  Create default (Manager → Accounts)
                </Button>
                <div className="flex w-full flex-col-reverse gap-2 sm:flex-row sm:justify-end">
                  <Button
                    type="button"
                    variant="outline"
                    disabled={saving}
                    onClick={() => setCreateOpen(false)}
                  >
                    Cancel
                  </Button>
                  <Button
                    type="button"
                    disabled={saving || !startRoleId}
                    onClick={handleCreateWorkflow}
                  >
                    {saving ? 'Please wait...' : 'Create workflow'}
                  </Button>
                </div>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      )}

      <AdminConfirmDialog
        open={deleteConfirmOpen}
        onOpenChange={(open) => !open && setDeleteConfirmOpen(false)}
        title="Delete workflow"
        description={
          selectedWorkflow
            ? `Permanently delete "${selectedWorkflow.name}" for ${selectedWorkflow.start_role_name ?? 'this role'}? This cannot be undone.`
            : 'Permanently delete this workflow? This cannot be undone.'
        }
        confirmLabel="Delete"
        onConfirm={handleDeleteWorkflow}
        loading={saving}
      />
    </DashboardLayout>
  )
}
