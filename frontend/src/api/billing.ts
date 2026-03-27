import client from './client';

export const getBillingStatus = () => client.get('/billing/status');
export const createCheckout = () => client.post('/billing/checkout');
export const createPortal = () => client.post('/billing/portal');
