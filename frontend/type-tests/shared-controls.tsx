import { SelectField } from '../src/shared/select-field';
import { ViewStatus } from '../src/shared/view-status';

<SelectField label="Dataset" value="demo" onChange={(event) => event.currentTarget.value} />;
<ViewStatus kind="error" onRetry={() => {}}>
  Could not load data.
</ViewStatus>;
// @ts-expect-error Every select requires a visible label.
<SelectField value="demo" />;
// @ts-expect-error Unknown states must not silently produce unstyled messages.
<ViewStatus kind="failed">Could not load data.</ViewStatus>;
// @ts-expect-error Retry actions must be callable.
<ViewStatus onRetry="retry">Could not load data.</ViewStatus>;
