import streamlit as st
import pandas as pd
import csv
import plotly.express as px

# Configuración de la página
st.set_page_config(page_title="Network Analysis", layout="wide")

st.title("🚀 Análisis Avanzado de Conectividad 5G/4G")

# --- DICCIONARIO DE IPS ---
MAPA_IPS = {
    # Nubes Públicas
    '34.175.50.171': 'Cloud - GCP',
    '68.221.230.224': 'Cloud - Azure 1',
    '70.156.225.114': 'Cloud - Azure 2',
    '70.156.233.145': 'Cloud - Azure 3',
   
    # Edge Sites
    '192.168.0.54': 'Edge - Madrid',
    '192.168.0.150': 'Edge - Sevilla',
}

uploaded_files = st.file_uploader("Sube uno o varios archivos CSV de métricas", type=["csv"], accept_multiple_files=True)

if uploaded_files:
    # 1. CARGA Y UNIÓN DE MÚLTIPLES ARCHIVOS
    lista_dfs = []
    for file in uploaded_files:
        df_temp = pd.read_csv(file, encoding='latin1', quoting=csv.QUOTE_NONE)
        lista_dfs.append(df_temp)
        
    df = pd.concat(lista_dfs, ignore_index=True)
    
    # 2. LIMPIEZA DE DATOS
    df.columns = df.columns.str.replace('"', '')
    df = df.replace('"', '', regex=True)
    
    columnas_num = ['rtt_ms', 'avg_ms', 'jitter_ms', 'loss_pct', 'seq']
    for col in columnas_num:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    columnas_id = ['cell_id', 'cell_id_local', 'tac', 'pci']
    for col in columnas_id:
        if col in df.columns:
            df[col] = df[col].astype(str).replace('nan', '').str.replace(r'\.0$', '', regex=True)

    # 3. MERGE DE TABLAS
    valores_avg = df.dropna(subset=['avg_ms'])[['test_id', 'avg_ms', 'jitter_ms', 'loss_pct']]
    pruebas_completas = df.dropna(subset=['rtt_ms']).drop(columns=['avg_ms', 'jitter_ms', 'loss_pct'], errors='ignore')
    tabla_final = pd.merge(pruebas_completas, valores_avg, on='test_id', how='left')
    
    # Mapeo de nombres
    tabla_final['nombre_destino'] = tabla_final['target_host'].map(MAPA_IPS).fillna(tabla_final['target_host'])

    # --- 🛡️ FILTRO ANTI-DOS (Nubes Públicas) ---
    # Extraemos cuántos paquetes se mandaron en la ráfaga (buscando 'count=X' o 'tries=X' en la signature)
    tabla_final['paquetes_esperados'] = tabla_final['signature'].str.extract(r'(?:count|tries)=(\d+)').astype(float)
    
    # Calculamos los paquetes reales perdidos a partir del porcentaje
    tabla_final['paquetes_perdidos'] = (tabla_final['paquetes_esperados'] * tabla_final['loss_pct'] / 100).round()
    
    # Condición: ¿Es una IP de Cloud Y ha perdido más de 1 paquete?
    es_cloud = tabla_final['nombre_destino'].str.contains('Cloud', na=False)
    mas_de_un_perdido = tabla_final['paquetes_perdidos'] > 1
    
    # Sacamos la lista de IDs de ráfaga que han fallado
    test_ids_descartados = tabla_final[es_cloud & mas_de_un_perdido]['test_id'].dropna().unique()
    
    # Mostramos el aviso si se ha limpiado algo
    if len(test_ids_descartados) > 0:
        st.warning(f"🛡️ **Filtro Anti-DoS Activado:** Se han descartado automáticamente **{len(test_ids_descartados)} ráfagas** dirigidas a Nubes Públicas por presentar pérdida de paquetes anómala (>1 paquete perdido).")
        
    # Descartamos las filas de la tabla final
    tabla_final = tabla_final[~tabla_final['test_id'].isin(test_ids_descartados)]

    # --- BARRA LATERAL (Filtros Globales) ---
    st.sidebar.header("⚙️ Filtros Globales")
    
    rat_list = tabla_final['rat'].dropna().unique().tolist()
    rat_sel = st.sidebar.multiselect("Tecnología (RAT):", rat_list, default=rat_list)
    
    dest_list = tabla_final['nombre_destino'].dropna().unique().tolist()
    dest_sel = st.sidebar.multiselect("Destinos:", dest_list, default=dest_list)
    
    mask = tabla_final['rat'].isin(rat_sel) & tabla_final['nombre_destino'].isin(dest_sel)
    df_filtrado = tabla_final[mask]

    # --- MÉTRICAS GLOBALES DIVIDIDAS (Cloud vs Edge) ---
    st.subheader(f"📊 Resumen de Rendimiento ({len(uploaded_files)} archivos cargados)")
    
    if not df_filtrado.empty:
        # Separar los datos en dos bloques basándonos en el nombre
        df_cloud = df_filtrado[df_filtrado['nombre_destino'].str.contains('Cloud', na=False)]
        df_edge = df_filtrado[df_filtrado['nombre_destino'].str.contains('Edge', na=False)]
        
        # --- BLOQUE CLOUD ---
        st.markdown("#### ☁️ Agregado Nubes Públicas (Cloud)")
        if not df_cloud.empty:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Latencia Media", f"{df_cloud['rtt_ms'].mean():.2f} ms")
            c2.metric("Jitter Medio", f"{df_cloud.drop_duplicates(subset=['test_id'])['jitter_ms'].mean():.2f} ms")
            c3.metric("Loss Medio", f"{df_cloud.drop_duplicates(subset=['test_id'])['loss_pct'].mean():.2f} %")
            c4.metric("Pings Analizados", len(df_cloud))
        else:
            st.info("No hay datos de nubes públicas en la selección actual.")
            
        st.write("") # Pequeño espacio visual
        
        # --- BLOQUE EDGE ---
        st.markdown("#### 🏭 Agregado Nodos Locales (Edge)")
        if not df_edge.empty:
            e1, e2, e3, e4 = st.columns(4)
            e1.metric("Latencia Media", f"{df_edge['rtt_ms'].mean():.2f} ms")
            e2.metric("Jitter Medio", f"{df_edge.drop_duplicates(subset=['test_id'])['jitter_ms'].mean():.2f} ms")
            e3.metric("Loss Medio", f"{df_edge.drop_duplicates(subset=['test_id'])['loss_pct'].mean():.2f} %")
            e4.metric("Pings Analizados", len(df_edge))
        else:
            st.info("No hay datos de nodos Edge en la selección actual.")
            
    else:
        st.warning("No hay datos válidos tras aplicar los filtros y la limpieza Anti-DoS.")
        
    st.write("---")

    # --- MENÚ SUPERIOR (TABS) ---
    tab_latencia, tab_jitter, tab_red = st.tabs(["📉 Análisis de Latencia", "〰️ Análisis de Jitter y Loss", "🗼 Info de Red & Celdas"])

    with tab_latencia:
        st.header("Análisis de RTT (Round Trip Time)")
        if not df_filtrado.empty:
            col_min, col_max, col_p95 = st.columns(3)
            col_min.metric("Mínimo RTT", f"{df_filtrado['rtt_ms'].min():.2f} ms")
            col_max.metric("Máximo RTT", f"{df_filtrado['rtt_ms'].max():.2f} ms")
            col_p95.metric("P95 Latencia", f"{df_filtrado['rtt_ms'].quantile(0.95):.2f} ms")
    
            st.subheader("Evolución Temporal del RTT")
            df_linea = df_filtrado.sort_values('ts_iso')
            fig_rtt = px.line(df_linea, x='ts_iso', y='rtt_ms', color='nombre_destino', 
                              title="Latencia por Destino en el Tiempo", markers=False)
            st.plotly_chart(fig_rtt, use_container_width=True)
    
            st.subheader("Distribución de Latencia (Boxplot)")
            fig_box = px.box(df_filtrado, x='nombre_destino', y='rtt_ms', color='rat', points="all")
            st.plotly_chart(fig_box, use_container_width=True)

    with tab_jitter:
        st.header("Análisis de Jitter y Pérdida de Paquetes")
        df_resumen = df_filtrado.drop_duplicates(subset=['test_id']).dropna(subset=['jitter_ms'])
        
        if not df_resumen.empty:
            # 1. Gráfico de Jitter
            st.subheader("Jitter Medio por Destino")
            jitter_avg = df_resumen.groupby('nombre_destino')['jitter_ms'].mean().reset_index()
            fig_jit = px.bar(jitter_avg, x='nombre_destino', y='jitter_ms', 
                             color='nombre_destino', text_auto='.2f', title="Comparativa de Jitter")
            st.plotly_chart(fig_jit, use_container_width=True)
            
            st.write("---")
            
            # 2. Análisis de Packet Loss rediseñado (Nuevos titulares)
            st.subheader("Análisis de Pérdida de Paquetes (Packet Loss)")
            
            df_cloud_resumen = df_resumen[df_resumen['nombre_destino'].str.contains('Cloud', na=False)]
            df_edge_resumen = df_resumen[df_resumen['nombre_destino'].str.contains('Edge', na=False)]
            
            col_loss1, col_loss2 = st.columns(2)
            
            with col_loss1:
                st.markdown("#### ☁️ Estado Nubes Públicas")
                if not df_cloud_resumen.empty:
                    loss_cloud_avg = df_cloud_resumen['loss_pct'].mean()
                    if loss_cloud_avg == 0:
                        st.success("✅ **0.00% de pérdida media** detectada en Nubes.")
                    else:
                        st.info(f"Pérdida media real en Nubes: **{loss_cloud_avg:.2f}%**")
                else:
                    st.write("Sin datos de Cloud en la selección.")
            
            with col_loss2:
                st.markdown("#### 🏭 Estado Nodos Edge")
                if not df_edge_resumen.empty:
                    loss_edge_avg = df_edge_resumen['loss_pct'].mean()
                    st.metric("Pérdida media global en Edge", f"{loss_edge_avg:.2f} %")
                else:
                    st.write("Sin datos de Edge en la selección.")

            # 3. Histograma exclusivo para el Edge
            if not df_edge_resumen.empty and df_edge_resumen['loss_pct'].sum() > 0:
                st.markdown("**Distribución de Pérdidas en el Edge**")
                fig_hist = px.histogram(df_edge_resumen, x='loss_pct', 
                                        nbins=20, 
                                        title="Frecuencia de % de Pérdida en Ráfagas al Edge",
                                        labels={'loss_pct': '% de Paquetes Perdidos', 'count': 'Número de Ráfagas'},
                                        color_discrete_sequence=['#FF7F0E']) # Color naranja
                fig_hist.update_layout(bargap=0.05)
                st.plotly_chart(fig_hist, use_container_width=True)
            elif not df_edge_resumen.empty:
                st.success("✅ 0% de pérdida de paquetes en el Edge en las muestras actuales.")
            
            st.write("---")
            
            # 4. Detalle en crudo
            st.subheader("Detalle de las Ráfagas (Bursts)")
            st.dataframe(df_resumen[['ts_iso', 'nombre_destino', 'jitter_ms', 'loss_pct']], use_container_width=True)
        else:
            st.warning("No hay datos de Jitter/Loss disponibles.")

    with tab_red:
        st.header("Detalles de la Red de Acceso")
        
        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("Celdas Detectadas")
            celdas = df_filtrado[['rat', 'access_network', 'cell_id', 'pci', 'tac']].drop_duplicates()
            st.table(celdas)
            
        with col_b:
            st.subheader("Uso de Tecnología")
            pie_data = df_filtrado['rat'].value_counts().reset_index()
            fig_pie = px.pie(pie_data, values='count', names='rat', title="% de muestras por RAT")
            st.plotly_chart(fig_pie)

        st.subheader("Log Completo Consolidado")
        st.dataframe(df_filtrado, use_container_width=True)

else:
    st.info("Arrastra aquí tu carpeta con los CSVs o selecciona varios archivos para comenzar el análisis...")