import { redirect } from "next/navigation";

export default function Home() {
  // The metric-detail screen is the product; connectors is the way in.
  redirect("/connectors");
}
