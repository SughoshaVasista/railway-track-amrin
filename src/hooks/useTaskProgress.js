import { useState } from 'react'

export default function useTaskProgress(initialTasks) {
  const [items, setItems] = useState(initialTasks)
  const advance = (id) =>
    setItems(
      items.map((task) =>
        task.id === id
          ? {
              ...task,
              status:
                {
                  ASSIGNED: 'ACCEPTED',
                  ACCEPTED: 'IN_PROGRESS',
                  IN_PROGRESS: 'COMPLETED',
                }[task.status] || task.status,
            }
          : task,
      ),
    )
  return { items, advance }
}
