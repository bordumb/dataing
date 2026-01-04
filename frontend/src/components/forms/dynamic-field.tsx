import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { FieldSchema } from './field-schema'

interface DynamicFieldProps {
  field: FieldSchema
  value: string | number | boolean
  onChange: (name: string, value: string | number | boolean) => void
  error?: string
}

export function DynamicField({ field, value, onChange, error }: DynamicFieldProps) {
  const handleChange = (newValue: string | number | boolean) => {
    onChange(field.name, newValue)
  }

  const renderField = () => {
    switch (field.type) {
      case 'text':
      case 'password':
        return (
          <Input
            id={field.name}
            type={field.type}
            value={String(value ?? '')}
            onChange={(e) => handleChange(e.target.value)}
            placeholder={field.placeholder}
            required={field.required}
          />
        )

      case 'number':
        return (
          <Input
            id={field.name}
            type="number"
            value={value === '' ? '' : Number(value)}
            onChange={(e) => handleChange(e.target.value === '' ? '' : Number(e.target.value))}
            placeholder={field.placeholder}
            min={field.min}
            max={field.max}
            required={field.required}
          />
        )

      case 'textarea':
        return (
          <Textarea
            id={field.name}
            value={String(value ?? '')}
            onChange={(e) => handleChange(e.target.value)}
            placeholder={field.placeholder}
            required={field.required}
            rows={4}
          />
        )

      case 'select':
        return (
          <Select
            value={String(value ?? '')}
            onValueChange={(v) => handleChange(v)}
          >
            <SelectTrigger>
              <SelectValue placeholder={field.placeholder || 'Select...'} />
            </SelectTrigger>
            <SelectContent>
              {field.options?.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )

      case 'checkbox':
        return (
          <div className="flex items-center space-x-2">
            <Checkbox
              id={field.name}
              checked={Boolean(value)}
              onCheckedChange={(checked) => handleChange(checked === true)}
            />
            <Label htmlFor={field.name} className="font-normal">
              {field.description || field.label}
            </Label>
          </div>
        )

      default:
        return (
          <Input
            id={field.name}
            value={String(value ?? '')}
            onChange={(e) => handleChange(e.target.value)}
            placeholder={field.placeholder}
          />
        )
    }
  }

  return (
    <div className="space-y-2">
      {field.type !== 'checkbox' && (
        <Label htmlFor={field.name}>
          {field.label}
          {field.required && <span className="text-destructive ml-1">*</span>}
        </Label>
      )}
      {renderField()}
      {field.description && field.type !== 'checkbox' && (
        <p className="text-sm text-muted-foreground">{field.description}</p>
      )}
      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  )
}
