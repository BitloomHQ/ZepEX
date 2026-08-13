import { ChevronDown, Download, FileUp, Upload } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'

interface PolicyImportMenuProps {
  onImportCsv: () => void
  onImportDocument: () => void
  onDownloadTemplate: () => void
  disabled?: boolean
}

export function PolicyImportMenu({
  onImportCsv,
  onImportDocument,
  onDownloadTemplate,
  disabled,
}: PolicyImportMenuProps) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return

    const handleClickOutside = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [open])

  return (
    <div className="flex flex-wrap gap-2">
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={onDownloadTemplate}
        disabled={disabled}
      >
        <Download className="h-4 w-4" />
        Download template
      </Button>

      <div ref={containerRef} className="relative">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={disabled}
          onClick={() => setOpen((current) => !current)}
        >
          <Upload className="h-4 w-4" />
          Import
          <ChevronDown className="h-4 w-4" />
        </Button>

        {open && (
          <div className="absolute right-0 z-20 mt-2 min-w-[12rem] overflow-hidden rounded-lg border border-[#e2e8f0] bg-white py-1 shadow-lg">
            <button
              type="button"
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-gray-700 hover:bg-gray-50"
              onClick={() => {
                setOpen(false)
                onImportCsv()
              }}
            >
              <Upload className="h-4 w-4 text-gray-500" />
              Import CSV
            </button>
            <button
              type="button"
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-gray-700 hover:bg-gray-50"
              onClick={() => {
                setOpen(false)
                onImportDocument()
              }}
            >
              <FileUp className="h-4 w-4 text-gray-500" />
              Import policy document
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
