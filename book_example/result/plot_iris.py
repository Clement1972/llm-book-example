
import pandas as pd
import plotly.express as px

# Read the CSV file
df = pd.read_csv("Iris.csv")

# Create the scatter plot
fig = px.scatter(df, x="花萼寬度", y="花瓣長度", color="類別",
                 title="花萼寬度 vs 花瓣長度 (依類別區分)")

# Save the plot to an HTML file
fig.write_html("iris_scatter_plot.html")

print("散佈圖已儲存至 iris_scatter_plot.html")
