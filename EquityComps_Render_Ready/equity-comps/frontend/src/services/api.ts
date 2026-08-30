import axios from 'axios';
import { CompsResponse, FilterOptions, DataTimestamps } from '../types';
const configuredApiUrl = (import.meta.env.VITE_API_URL as string | undefined)?.trim().replace(/\/$/, '');
const BASE = configuredApiUrl
  ? `${configuredApiUrl}/api/v1`
  : '/api/v1'; export const api=axios.create({baseURL:BASE,timeout:30000});
export interface CompsParams{universe?:string;sector?:string;industry?:string;search?:string;}
export async function fetchComps(params:CompsParams):Promise<CompsResponse>{const p:Record<string,string>={};if(params.universe&&params.universe!=='ALL')p.universe=params.universe;if(params.sector)p.sector=params.sector;if(params.industry)p.industry=params.industry;if(params.search)p.search=params.search;return (await api.get('/comps',{params:p})).data;}
export async function fetchFilterOptions(sector?:string):Promise<FilterOptions>{return (await api.get('/filters',{params:sector?{sector}:{}})).data;}
export async function fetchTimestamps():Promise<DataTimestamps>{return (await api.get('/timestamps')).data;}
export function getExportUrl(format:'csv'|'excel',params:CompsParams):string{const p=new URLSearchParams();if(params.universe&&params.universe!=='ALL')p.set('universe',params.universe);if(params.sector)p.set('sector',params.sector);if(params.industry)p.set('industry',params.industry);if(params.search)p.set('search',params.search);return `${BASE}/export/${format}${p.toString()?`?${p.toString()}`:''}`;}
