import React, { lazy, Suspense } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import TextArea from '../TextArea';

const LazyTextArea = lazy(async () => ({ default: TextArea }));

it('hydrates a lazily mounted editor and switches saved notes without emitting a save', async () => {
  const onChange = jest.fn();
  const view = (value: string) => (
    <React.StrictMode><Suspense fallback={<p>Opening note</p>}>
      <LazyTextArea value={value} onChange={onChange} />
    </Suspense></React.StrictMode>
  );
  const { rerender } = render(view('<p>First saved note</p>'));
  await screen.findByText('First saved note');
  rerender(view('<p>Second saved note</p>'));
  await screen.findByText('Second saved note');
  expect(screen.queryByText('First saved note')).not.toBeInTheDocument();
  expect(onChange).not.toHaveBeenCalled();
});

it('applies saved text arriving after the editor mounts without reporting a user edit', async () => {
  const onChange = jest.fn();
  const { container, rerender } = render(<TextArea value="" onChange={onChange} />);
  await waitFor(() => expect(container.querySelector('[contenteditable="true"]')).not.toBeNull());
  rerender(<TextArea value="<p>Loaded saved text</p>" onChange={onChange} />);
  await screen.findByText('Loaded saved text');
  expect(onChange).not.toHaveBeenCalled();
});

it('enables an editor after loading without treating its previous content as a user edit', async () => {
  const onChange = jest.fn();
  const { container, rerender } = render(<TextArea value="" editable={false} onChange={onChange} />);
  await waitFor(() => expect(container.querySelector('[contenteditable="false"]')).not.toBeNull());
  rerender(<TextArea value="<p>Saved idea</p>" editable onChange={onChange} />);
  await screen.findByText('Saved idea');
  expect(container.querySelector('[contenteditable="true"]')).not.toBeNull();
  expect(onChange).not.toHaveBeenCalled();
});
