import { useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Rail } from './navigation-rail.jsx';
import { AccountMenu } from './account-menu.jsx';

export function AccountNavigation({ actions, onNavigate, helpUrl, name }) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({});
  const avatar = useRef(null);
  const menu = useRef(null);

  function toggle() {
    if (!open) {
      document.getElementById('userSettingsCloseBtn')?.click();
      const bounds = avatar.current.getBoundingClientRect();
      setPosition({
        left: Math.max(8, Math.min(bounds.right + 8, window.innerWidth - 296)),
        bottom: Math.max(8, window.innerHeight - bounds.bottom),
      });
    }
    setOpen(!open);
  }

  useLayoutEffect(() => {
    if (!open) return;
    menu.current.querySelector('#userSettingsBtn')?.focus();
    const outside = (event) => {
      if (!menu.current.contains(event.target) && !avatar.current.contains(event.target)) {
        setOpen(false);
      }
    };
    const escape = (event) => {
      if (event.key === 'Escape') {
        setOpen(false);
        avatar.current.focus();
        event.stopPropagation();
      }
    };
    const resize = () => setOpen(false);
    document.addEventListener('click', outside);
    document.addEventListener('keydown', escape);
    window.addEventListener('resize', resize);
    return () => {
      document.removeEventListener('click', outside);
      document.removeEventListener('keydown', escape);
      window.removeEventListener('resize', resize);
    };
  }, [open]);

  return (
    <>
      <Rail
        actions={actions}
        onNavigate={onNavigate}
        accountOpen={open}
        onAccountToggle={toggle}
        avatarRef={avatar}
      />
      {createPortal(
        <div
          ref={menu}
          id="accountMenu"
          className="account-menu"
          role="dialog"
          aria-label="Account and application settings"
          hidden={!open}
          style={position}
          onClick={(event) => {
            const action = event.target.closest('button, a');
            if (action && action.id !== 'adminTabBtn') setOpen(false);
          }}
        >
          <AccountMenu actions={actions} onNavigate={onNavigate} helpUrl={helpUrl} name={name} />
        </div>,
        document.body,
      )}
    </>
  );
}
