import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ImportExportModal from '../ImportExportModal';

const mockSetMessage = jest.fn();
const mockOnClose = jest.fn();
const mockExportIdeas = jest.fn();
const mockImportIdeas = jest.fn();

jest.mock('features/notifications/context/MessageContext', () => ({
  useMessage: () => ({
    setMessage: mockSetMessage,
    clearMessage: jest.fn(),
    message: { text: null, type: 'info' as const },
  }),
}));

jest.mock('@apollo/client/react', () => {
  const actual = jest.requireActual('@apollo/client/react');
  return {
    ...actual,
    useMutation: (query: any) => {
      const queryStr = query?.loc?.source?.body || '';
      if (queryStr.includes('ExportIdeas') || queryStr.includes('exportIdeas')) {
        return [mockExportIdeas, { loading: false, error: null }];
      }
      if (queryStr.includes('ImportIdeas') || queryStr.includes('importIdeas')) {
        return [mockImportIdeas, { loading: false, error: null }];
      }
      return [jest.fn(), { loading: false, error: null }];
    },
  };
});

global.URL.createObjectURL = jest.fn(() => 'blob:mock-url');
global.URL.revokeObjectURL = jest.fn();

const mockLink = {
  click: jest.fn(),
  href: '',
  download: '',
  style: {},
};

const originalCreateElement = document.createElement.bind(document);

const createMockFileList = (files: File[]): FileList =>
  ({
    ...files,
    length: files.length,
    item: (index: number) => files[index] ?? null,
    [Symbol.iterator]: function* iterator() {
      yield* files;
    },
  }) as unknown as FileList;

const attachFileToInput = (input: HTMLInputElement, file: File) => {
  Object.defineProperty(input, 'files', {
    value: createMockFileList([file]),
    configurable: true,
  });
  fireEvent.change(input);
};

describe('ImportExportModal Component', () => {
  let createElementSpy: jest.SpyInstance;
  let appendChildSpy: jest.SpyInstance;
  let removeChildSpy: jest.SpyInstance;

  beforeEach(() => {
    jest.clearAllMocks();
    mockLink.click.mockClear();
    mockLink.href = '';
    mockLink.download = '';
    mockExportIdeas.mockResolvedValue({
      data: {
        exportIdeas: {
          content: btoa(JSON.stringify({ ideas: [] })),
          format: 'json',
          filename: 'manifest_ideas_20240101_120000.json',
        },
      },
    });
    mockImportIdeas.mockResolvedValue({
      data: {
        importIdeas: {
          importedCount: 2,
          skippedCount: 0,
          errors: [],
        },
      },
    });
  });
  
  afterEach(() => {
    createElementSpy?.mockRestore();
    appendChildSpy?.mockRestore();
    removeChildSpy?.mockRestore();
  });

  const setupDownloadMocks = () => {
    createElementSpy = jest.spyOn(document, 'createElement').mockImplementation((tagName: string) => {
      if (tagName === 'a') {
        return mockLink as unknown as HTMLAnchorElement;
      }
      return originalCreateElement(tagName);
    });
    appendChildSpy = jest.spyOn(document.body, 'appendChild').mockImplementation((node) => node as Node);
    removeChildSpy = jest.spyOn(document.body, 'removeChild').mockImplementation((node) => node as Node);
  };

  it('should not render when isOpen is false', () => {
    render(<ImportExportModal isOpen={false} onClose={mockOnClose} />);
    expect(screen.queryByText('Import & Export Ideas')).not.toBeInTheDocument();
  });

  it('should render when isOpen is true', () => {
    render(<ImportExportModal isOpen={true} onClose={mockOnClose} />);
    expect(screen.getByText('Import & Export Ideas')).toBeInTheDocument();
  });

  it('should show export tab by default', () => {
    render(<ImportExportModal isOpen={true} onClose={mockOnClose} />);
    expect(screen.getByText('Export Format')).toBeInTheDocument();
  });

  it('should switch to import tab when clicked', async () => {
    const user = userEvent.setup();
    render(<ImportExportModal isOpen={true} onClose={mockOnClose} />);

    const importTabButton = screen.getByRole('button', { name: /^Import$/i });
    await user.click(importTabButton);

    expect(screen.queryByText('Export Format')).not.toBeInTheDocument();
    expect(screen.getByText(/Bring ideas from your notes/)).toBeInTheDocument();
  });

  describe('Export Functionality', () => {
    it('should export ideas as JSON', async () => {
      const user = userEvent.setup();
      render(<ImportExportModal isOpen={true} onClose={mockOnClose} />);
      setupDownloadMocks();

      const exportButton = screen.getByRole('button', { name: /Export Ideas/i });
      await user.click(exportButton);

      await waitFor(() => {
        expect(mockExportIdeas).toHaveBeenCalledWith({ variables: { format: 'json' } });
      });

      await waitFor(() => {
        expect(mockSetMessage).toHaveBeenCalledWith(
          expect.stringContaining('Successfully exported'),
          'success'
        );
      });

      expect(mockOnClose).toHaveBeenCalled();
      expect(mockLink.click).toHaveBeenCalled();
    });

    it('should export ideas as CSV', async () => {
      const user = userEvent.setup();
      mockExportIdeas.mockResolvedValueOnce({
        data: {
          exportIdeas: {
            content: btoa('title,description\nIdea 1,Desc 1'),
            format: 'csv',
            filename: 'manifest_ideas_20240101_120000.csv',
          },
        },
      });

      render(<ImportExportModal isOpen={true} onClose={mockOnClose} />);
      setupDownloadMocks();

      const csvOption = screen.getByLabelText(/csv/i);
      await user.click(csvOption);

      const exportButton = screen.getByRole('button', { name: /Export Ideas/i });
      await user.click(exportButton);

      await waitFor(() => {
        expect(mockExportIdeas).toHaveBeenCalledWith({ variables: { format: 'csv' } });
      });
    });

    it('should export ideas as Markdown', async () => {
      const user = userEvent.setup();
      mockExportIdeas.mockResolvedValueOnce({
        data: {
          exportIdeas: {
            content: btoa('# Ideas\n\n## 1. Idea 1'),
            format: 'markdown',
            filename: 'manifest_ideas_20240101_120000.md',
          },
        },
      });

      render(<ImportExportModal isOpen={true} onClose={mockOnClose} />);
      setupDownloadMocks();

      const mdOption = screen.getByLabelText(/markdown/i);
      await user.click(mdOption);

      const exportButton = screen.getByRole('button', { name: /Export Ideas/i });
      await user.click(exportButton);

      await waitFor(() => {
        expect(mockExportIdeas).toHaveBeenCalledWith({ variables: { format: 'markdown' } });
      });
    });

    it('should handle export errors', async () => {
      const user = userEvent.setup();
      mockExportIdeas.mockRejectedValueOnce(new Error('Export failed'));

      render(<ImportExportModal isOpen={true} onClose={mockOnClose} />);

      const exportButton = screen.getByRole('button', { name: /Export Ideas/i });
      await user.click(exportButton);

      await waitFor(() => {
        expect(mockSetMessage).toHaveBeenCalledWith(
          expect.stringContaining('Export failed'),
          'error'
        );
      });
    });
  });

  describe('Import Functionality', () => {
    it('should show file upload area in import tab', async () => {
      const user = userEvent.setup();
      render(<ImportExportModal isOpen={true} onClose={mockOnClose} />);

      const importTabButton = screen.getByRole('button', { name: /^Import$/i });
      await user.click(importTabButton);

      expect(screen.getByText(/Drag and drop a file here/)).toBeInTheDocument();
      expect(screen.getByText(/browse to upload/)).toBeInTheDocument();
      expect(screen.getAllByText(/Apple Notes/i)).not.toHaveLength(0);
      expect(screen.getAllByText(/Google Keep/i)).not.toHaveLength(0);
    });

    it('should handle file selection', async () => {
      const user = userEvent.setup();
      render(<ImportExportModal isOpen={true} onClose={mockOnClose} />);

      const importTabButton = screen.getByRole('button', { name: /^Import$/i });
      await user.click(importTabButton);

      const file = new File(['{"ideas": []}'], 'test.json', { type: 'application/json' });
      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;

      if (fileInput) {
        attachFileToInput(fileInput, file);
      }

      await waitFor(() => {
        expect(screen.getByText('test.json')).toBeInTheDocument();
      });
    });

    it('should import ideas from JSON file', async () => {
      const user = userEvent.setup();
      const jsonContent = JSON.stringify({
        ideas: [
          { title: 'Imported Idea 1', description: 'Desc 1' },
          { title: 'Imported Idea 2', description: 'Desc 2' },
        ],
      });

      render(<ImportExportModal isOpen={true} onClose={mockOnClose} />);

      const importTabButton = screen.getByRole('button', { name: /^Import$/i });
      await user.click(importTabButton);

      const file = new File([jsonContent], 'test.json', { type: 'application/json' });
      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;

      if (fileInput) {
        attachFileToInput(fileInput, file);
      }

      await waitFor(() => {
        expect(screen.getByText('test.json')).toBeInTheDocument();
      });

      const importButton = screen.getByRole('button', { name: /Import Ideas/i });
      await user.click(importButton);

      await waitFor(() => {
        expect(mockImportIdeas).toHaveBeenCalled();
      });

      await waitFor(() => {
        expect(mockSetMessage).toHaveBeenCalledWith(
          expect.stringContaining('Successfully imported'),
          'success'
        );
      });

      expect(mockOnClose).toHaveBeenCalled();
    });

    it('should reject invalid file types', async () => {
      const user = userEvent.setup();
      render(<ImportExportModal isOpen={true} onClose={mockOnClose} />);

      const importTabButton = screen.getByRole('button', { name: /^Import$/i });
      await user.click(importTabButton);

      const file = new File(['invalid'], 'test.exe', { type: 'application/octet-stream' });
      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;

      if (fileInput) {
        attachFileToInput(fileInput, file);
      }

      await waitFor(() => {
        expect(mockSetMessage).toHaveBeenCalledWith(
          expect.stringContaining('Invalid file type'),
          'error'
        );
      });
    });

    it('should reject files that are too large', async () => {
      const user = userEvent.setup();
      const file = new File(['large'], 'large.json', { type: 'application/json' });
      Object.defineProperty(file, 'size', {
        value: 26 * 1024 * 1024,
        configurable: true,
      });

      render(<ImportExportModal isOpen={true} onClose={mockOnClose} />);

      const importTabButton = screen.getByRole('button', { name: /^Import$/i });
      await user.click(importTabButton);

      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;

      if (fileInput) {
        attachFileToInput(fileInput, file);
      }

      await waitFor(() => {
        expect(mockSetMessage).toHaveBeenCalledWith(
          expect.stringContaining('File size too large'),
          'error'
        );
      });
    });

    it('should handle import errors', async () => {
      const user = userEvent.setup();
      mockImportIdeas.mockRejectedValueOnce(new Error('Import failed'));
      const jsonContent = JSON.stringify({ ideas: [] });

      const mockFileReader = {
        readAsArrayBuffer: jest.fn(),
        onload: null as any,
        result: new TextEncoder().encode(jsonContent).buffer,
      };
      jest.spyOn(global, 'FileReader').mockImplementation(() => mockFileReader as any);

      render(<ImportExportModal isOpen={true} onClose={mockOnClose} />);

      const importTabButton = screen.getByRole('button', { name: /^Import$/i });
      await user.click(importTabButton);

      const file = new File([jsonContent], 'test.json', { type: 'application/json' });
      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;

      if (fileInput) {
        attachFileToInput(fileInput, file);
      }

      await waitFor(() => {
        expect(screen.getByText('test.json')).toBeInTheDocument();
      });

      mockFileReader.readAsArrayBuffer.mockImplementation(() => {
        if (mockFileReader.onload) {
          mockFileReader.onload({ target: { result: mockFileReader.result } });
        }
      });

      const importButton = screen.getByRole('button', { name: /Import Ideas/i });
      await user.click(importButton);

      await waitFor(() => {
        expect(mockSetMessage).toHaveBeenCalledWith(
          expect.stringMatching(/failed/i),
          'error'
        );
      });

      (global.FileReader as jest.Mock).mockRestore?.();
    });

    it('should show import results with skipped items', async () => {
      const user = userEvent.setup();
      mockImportIdeas.mockResolvedValueOnce({
        data: {
          importIdeas: {
            importedCount: 1,
            skippedCount: 1,
            errors: ['Failed to import Idea 2'],
          },
        },
      });
      const jsonContent = JSON.stringify({
        ideas: [
          { title: 'Idea 1', description: 'Desc 1' },
          { title: 'Idea 2', description: 'Desc 2' },
        ],
      });

      render(<ImportExportModal isOpen={true} onClose={mockOnClose} />);

      const importTabButton = screen.getByRole('button', { name: /^Import$/i });
      await user.click(importTabButton);

      const file = new File([jsonContent], 'test.json', { type: 'application/json' });
      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;

      if (fileInput) {
        attachFileToInput(fileInput, file);
      }

      await waitFor(() => {
        expect(screen.getByText('test.json')).toBeInTheDocument();
      });

      const importButton = screen.getByRole('button', { name: /Import Ideas/i });
      await user.click(importButton);

      await waitFor(() => {
        expect(mockSetMessage).toHaveBeenCalledWith(
          expect.stringContaining('skipped'),
          'success'
        );
      });
    });
  });

  it('should close modal when cancel button is clicked', async () => {
    const user = userEvent.setup();
    render(<ImportExportModal isOpen={true} onClose={mockOnClose} />);

    const cancelButton = screen.getByText('Cancel');
    await user.click(cancelButton);

    expect(mockOnClose).toHaveBeenCalled();
  });

  it('should close modal when X button is clicked', async () => {
    const user = userEvent.setup();
    render(<ImportExportModal isOpen={true} onClose={mockOnClose} />);

    const closeButton = screen.getByLabelText('Close');
    await user.click(closeButton);

    expect(mockOnClose).toHaveBeenCalled();
  });

  it('should show Apple Notes and Google Keep instructions in import tab', async () => {
    const user = userEvent.setup();
    render(<ImportExportModal isOpen={true} onClose={mockOnClose} />);

    const importTabButton = screen.getByRole('button', { name: /^Import$/i });
    await user.click(importTabButton);

    expect(screen.getAllByText('Apple Notes')).not.toHaveLength(0);
    expect(screen.getAllByText('Google Keep')).not.toHaveLength(0);
    expect(screen.getAllByText(/Google Takeout/i)).not.toHaveLength(0);
    expect(screen.getByText(/uses AI to separate startup ideas/i)).toBeInTheDocument();
  });
});
