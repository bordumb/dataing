import { Link } from 'react-router-dom'

interface DatasetLinkProps {
  id: string
  name: string
  className?: string
}

export function DatasetLink({ id, name, className }: DatasetLinkProps) {
  return (
    <Link
      to={`/datasets/${id}`}
      className={`text-primary hover:underline ${className || ''}`}
    >
      {name}
    </Link>
  )
}
